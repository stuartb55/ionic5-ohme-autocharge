"""Optional Octopus Agile (dynamic tariff) awareness.

Fetches upcoming half-hourly unit rates from Octopus Energy's public API (no
account or auth needed). Enabled only when ``OCTOPUS_PRODUCT_CODE`` and
``OCTOPUS_REGION`` are set; otherwise every call is a no-op, mirroring the
graceful-degradation pattern used by ntfy/db. Failures return None and are
swallowed so the tariff card simply hides.
"""

from __future__ import annotations

import base64
import datetime
import logging
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import aiohttp

import config

logger = logging.getLogger(__name__)

_BASE = "https://api.octopus.energy/v1"

# Cached (mpan, serial) of the electricity import meter, discovered once from the
# account endpoint (it never changes for a given home). None until the first
# successful lookup — mirrors the singleton pattern in bluelink._manager.
_meter: Optional[tuple[str, str]] = None


@dataclass
class PricedEnergy:
    """Delivered energy priced in integer currency-minor units."""

    intervals: list[dict] = field(default_factory=list)
    cost_minor: Optional[int] = None
    coverage: float = 0.0
    energy_wh: int = 0


def is_enabled() -> bool:
    """True when an Agile product code and region are configured."""
    return bool(config.OCTOPUS_PRODUCT_CODE and config.OCTOPUS_REGION)


def consumption_is_enabled() -> bool:
    """True when an Octopus account (API key + number) is configured.

    Separate from :func:`is_enabled`: the Agile rates use the public API, while
    half-hourly household consumption needs an authenticated account call.
    """
    return bool(config.OCTOPUS_API_KEY and config.OCTOPUS_ACCOUNT_NUMBER)


def _tariff_code() -> str:
    return f"E-1R-{config.OCTOPUS_PRODUCT_CODE}-{config.OCTOPUS_REGION}"


def _auth_headers() -> dict[str, str]:
    """HTTP Basic auth header for the account API (key as user, empty password).

    Built by hand rather than via ``aiohttp.BasicAuth`` (deprecated in 3.14 / to
    be removed in 4.0) so it works regardless of the installed aiohttp version.
    """
    token = base64.b64encode(f"{config.OCTOPUS_API_KEY}:".encode()).decode()
    return {"Authorization": f"Basic {token}"}


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

    total = Decimal("0")
    for slot in slots:
        span = (slot.end - slot.start).total_seconds()
        if span <= 0:
            continue  # zero-length slot carries no time-priced energy
        covered = 0.0
        slot_cost = Decimal("0")
        for w_start, w_end, price in windows:
            overlap = (min(slot.end, w_end) - max(slot.start, w_start)).total_seconds()
            if overlap > 0:
                slot_cost += (
                    Decimal(str(slot.energy))
                    * (Decimal(str(overlap)) / Decimal(str(span)))
                    * Decimal(str(price))
                )
                covered += overlap
        # A gap (uncovered time) means we can't price the whole slot — bail out
        # rather than under-report. 1s tolerance absorbs float/rounding error.
        if abs(covered - span) > 1:
            return None
        total += slot_cost
    return float(total.quantize(Decimal("0.01"), rounding=ROUND_HALF_UP))


def price_energy_buckets(
    car_by_slot: dict[str, float], rates: Optional[list[dict]]
) -> PricedEnergy:
    """Price measured half-hour energy buckets against tariff windows.

    Monetary arithmetic is Decimal throughout and converted to integer minor
    units (pence for GBP) only at the persistence boundary. A session gets an
    actual total only when every delivered Wh is covered exactly once.
    """
    result = PricedEnergy()
    windows: list[tuple[datetime.datetime, datetime.datetime, Decimal]] = []
    for rate in rates or []:
        start = _parse(rate.get("from"))
        end = _parse(rate.get("to"))
        price = rate.get("pricePerKwh")
        if start and end and end > start and isinstance(price, (int, float)):
            windows.append((start, end, Decimal(str(price)) * Decimal(100)))
    windows.sort(key=lambda window: window[0])

    covered_wh = 0
    exact_cost_minor = Decimal("0")
    for key, raw_kwh in sorted(car_by_slot.items()):
        start = _parse(key)
        energy_kwh = Decimal(str(max(0.0, raw_kwh)))
        energy_wh = int((energy_kwh * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
        if start is None or energy_wh <= 0:
            continue
        end = start + datetime.timedelta(minutes=30)
        span = Decimal(str((end - start).total_seconds()))
        covered_seconds = Decimal("0")
        bucket_cost = Decimal("0")
        weighted_rate = Decimal("0")
        for rate_start, rate_end, price_minor in windows:
            overlap_seconds = (min(end, rate_end) - max(start, rate_start)).total_seconds()
            if overlap_seconds <= 0:
                continue
            overlap = Decimal(str(overlap_seconds))
            fraction = overlap / span
            covered_seconds += overlap
            bucket_cost += energy_kwh * fraction * price_minor
            weighted_rate += price_minor * fraction
        fully_covered = abs(covered_seconds - span) <= Decimal("1")
        cost_minor = (
            int(bucket_cost.quantize(Decimal("1"), rounding=ROUND_HALF_UP))
            if fully_covered
            else None
        )
        if fully_covered:
            covered_wh += energy_wh
            exact_cost_minor += bucket_cost
        result.energy_wh += energy_wh
        result.intervals.append(
            {
                "start": start,
                "end": end,
                "energyWh": energy_wh,
                "costMinor": cost_minor,
                "rateMinorPerKwh": float(weighted_rate) if fully_covered else None,
                "currency": "GBP" if fully_covered else None,
                "quality": "priced" if fully_covered else "rate_gap_or_overlap",
            }
        )

    result.coverage = covered_wh / result.energy_wh if result.energy_wh else 0.0
    if result.energy_wh and covered_wh == result.energy_wh:
        result.cost_minor = int(
            exact_cost_minor.quantize(Decimal("1"), rounding=ROUND_HALF_UP)
        )
    return result


# --- household consumption (authenticated account API) -----------------------


async def _discover_meter() -> Optional[tuple[str, str]]:
    """Return the electricity import meter ``(mpan, serial)`` for the account.

    Cached after the first success — a home's meter doesn't change. Reads the
    account endpoint and picks the first non-export electricity meter point.
    None when disabled or on any failure (so the feature degrades to off).
    """
    global _meter
    if _meter is not None:
        return _meter
    if not consumption_is_enabled():
        return None
    url = f"{_BASE}/accounts/{config.OCTOPUS_ACCOUNT_NUMBER}/"
    headers = _auth_headers()
    timeout = aiohttp.ClientTimeout(total=10)
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            async with session.get(url, headers=headers) as resp:
                if resp.status != 200:
                    logger.warning("Octopus account API returned HTTP %s", resp.status)
                    return None
                data = await resp.json()
        for prop in data.get("properties") or []:
            for point in prop.get("electricity_meter_points") or []:
                # Skip export (solar feed-in) meter points — we want grid import.
                if point.get("is_export"):
                    continue
                mpan = point.get("mpan")
                meters = point.get("meters") or []
                serial = meters[0].get("serial_number") if meters else None
                if mpan and serial:
                    _meter = (mpan, serial)
                    logger.info("Discovered Octopus import meter %s/%s", mpan, serial)
                    return _meter
    except Exception:
        logger.warning("Failed to discover Octopus meter", exc_info=True)
        return None
    logger.warning("No electricity import meter found on the Octopus account")
    return None


async def fetch_consumption(
    period_from: datetime.datetime, period_to: datetime.datetime
) -> Optional[list[dict]]:
    """Half-hourly household grid import between ``period_from`` and ``period_to``.

    Returns ``[{from, to, importKwh}]`` chronological, following Octopus's
    pagination. None when disabled, the meter can't be discovered, or on any
    failure (so the energy-usage feature degrades to off, like the tariff card).
    """
    if not consumption_is_enabled():
        return None
    meter = await _discover_meter()
    if meter is None:
        return None
    mpan, serial = meter
    headers = _auth_headers()
    timeout = aiohttp.ClientTimeout(total=15)
    url: Optional[str] = (
        f"{_BASE}/electricity-meter-points/{mpan}/meters/{serial}/consumption/"
    )
    params: Optional[dict] = {
        "period_from": period_from.isoformat(),
        "period_to": period_to.isoformat(),
        "order_by": "period",  # chronological
        "page_size": 25000,  # one request covers any realistic window
    }
    out: list[dict] = []
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            # Follow `next` links until exhausted. The first request carries the
            # params; subsequent `next` URLs already embed them.
            while url:
                async with session.get(url, params=params, headers=headers) as resp:
                    if resp.status != 200:
                        logger.warning("Octopus consumption API returned HTTP %s", resp.status)
                        return None
                    data = await resp.json()
                for row in data.get("results") or []:
                    start = row.get("interval_start")
                    end = row.get("interval_end")
                    kwh = row.get("consumption")
                    if start and isinstance(kwh, (int, float)):
                        out.append(
                            {"from": start, "to": end, "importKwh": round(float(kwh), 4)}
                        )
                url = data.get("next")
                params = None  # the `next` URL already includes the query string
    except Exception:
        logger.warning("Failed to fetch Octopus consumption", exc_info=True)
        return None

    out.sort(key=lambda r: r["from"])
    return out
