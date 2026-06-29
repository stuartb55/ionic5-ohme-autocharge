"""Optional Octopus Agile (dynamic tariff) awareness.

Fetches upcoming half-hourly unit rates from Octopus Energy's public API (no
account or auth needed). Enabled only when ``OCTOPUS_PRODUCT_CODE`` and
``OCTOPUS_REGION`` are set; otherwise every call is a no-op, mirroring the
graceful-degradation pattern used by ntfy/db. Failures return None and are
swallowed so the tariff card simply hides.
"""

from __future__ import annotations

import datetime
import logging
from typing import Optional

import aiohttp

import config

logger = logging.getLogger(__name__)

_BASE = "https://api.octopus.energy/v1"


def is_enabled() -> bool:
    """True when an Agile product code and region are configured."""
    return bool(config.OCTOPUS_PRODUCT_CODE and config.OCTOPUS_REGION)


def _tariff_code() -> str:
    return f"E-1R-{config.OCTOPUS_PRODUCT_CODE}-{config.OCTOPUS_REGION}"


async def fetch_rates() -> Optional[list[dict]]:
    """Return upcoming half-hourly rates as ``[{from, to, pricePerKwh}]`` (£/kWh),
    sorted ascending by time. None when disabled or the fetch fails."""
    if not is_enabled():
        return None
    now = datetime.datetime.now(datetime.timezone.utc)
    # Start at the current half-hour boundary so the first slot is the live one.
    floor_min = 0 if now.minute < 30 else 30
    period_from = now.replace(minute=floor_min, second=0, microsecond=0)
    url = (
        f"{_BASE}/products/{config.OCTOPUS_PRODUCT_CODE}"
        f"/electricity-tariffs/{_tariff_code()}/standard-unit-rates/"
    )
    params = {"period_from": period_from.isoformat()}
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, params=params) as resp:
                if resp.status != 200:
                    logger.warning("Octopus API returned HTTP %s", resp.status)
                    return None
                data = await resp.json()

        # Octopus occasionally returns the same half-hour twice (e.g. a late
        # price correction). Keep one row per start time so a duplicated slot
        # can't show up as two identical entries in the dashboard's
        # cheapest-upcoming list. Kept inside the try so a malformed/non-numeric
        # row degrades to None like every other failure rather than 500ing.
        by_from: dict[str, dict] = {}
        for row in data.get("results") or []:
            valid_from = row.get("valid_from")
            price = row.get("value_inc_vat")  # pence per kWh, inc VAT
            if valid_from and isinstance(price, (int, float)):
                # Convert pence → pounds so the whole app works in £/kWh.
                by_from[valid_from] = {
                    "from": valid_from,
                    "to": row.get("valid_to"),
                    "pricePerKwh": round(float(price) / 100, 4),
                }
    except Exception:
        logger.warning("Failed to fetch Octopus Agile rates", exc_info=True)
        return None

    # The API returns newest-first; present oldest-first (chronological).
    rates = sorted(by_from.values(), key=lambda r: r["from"])
    return rates


def _parse(ts: str) -> Optional[datetime.datetime]:
    """Parse an ISO timestamp (handling a trailing ``Z``) to an aware datetime."""
    try:
        return datetime.datetime.fromisoformat(ts.replace("Z", "+00:00"))
    except (ValueError, AttributeError):
        return None


def cost_for_slots(slots: list, rates: Optional[list[dict]]) -> Optional[float]:
    """Cost (£) of the allocated charge ``slots`` priced against half-hourly Agile
    ``rates`` — far more accurate than a flat average when prices swing overnight.

    Each slot's energy is assumed drawn at constant power across its span, so the
    portion falling in a given rate window is ``energy × overlap / slot_duration``.
    Returns None (so the caller falls back to the average-price estimate) when
    rates are missing or don't fully cover every slot — e.g. a slot extends past
    the last published Agile price.
    """
    if not slots or not rates:
        return None
    windows = []
    for r in rates:
        start = _parse(r.get("from"))
        end = _parse(r.get("to"))
        price = r.get("pricePerKwh")
        if start and end and isinstance(price, (int, float)):
            windows.append((start, end, float(price)))
    if not windows:
        return None

    total = 0.0
    for slot in slots:
        span = (slot.end - slot.start).total_seconds()
        if span <= 0:
            continue  # zero-length slot carries no time-priced energy
        covered = 0.0
        slot_cost = 0.0
        for w_start, w_end, price in windows:
            overlap = (min(slot.end, w_end) - max(slot.start, w_start)).total_seconds()
            if overlap > 0:
                slot_cost += slot.energy * (overlap / span) * price
                covered += overlap
        # A gap (uncovered time) means we can't price the whole slot — bail out
        # rather than under-report. 1s tolerance absorbs float/rounding error.
        if covered < span - 1:
            return None
        total += slot_cost
    return round(total, 2)
