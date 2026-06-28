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
