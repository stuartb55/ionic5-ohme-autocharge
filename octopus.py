"""Optional Octopus tariff awareness.

Fetches upcoming unit rates from Octopus Energy's public API (no account or auth
needed). Agile rates are applied by time window. For Intelligent Octopus Go,
Ohme smart-charge slots are billed at the tariff's cheaper rate even when Ohme
schedules them outside the normal overnight window. Enabled only when
``OCTOPUS_PRODUCT_CODE`` and ``OCTOPUS_REGION`` are set; otherwise every call is
a no-op, mirroring the graceful-degradation pattern used by ntfy/db. Failures
return None and are swallowed so the tariff card simply hides.
"""

from __future__ import annotations

import base64
import datetime
import logging
import time
from dataclasses import dataclass, field
from decimal import Decimal, ROUND_HALF_UP
from typing import Optional

import aiohttp

import config

logger = logging.getLogger(__name__)

_BASE = "https://api.octopus.energy/v1"

# The account endpoint can retain multiple serials after a meter exchange. Cache
# all current-property import identities for a bounded period so ingestion spans
# replacements and eventually notices account changes.
_meters: list[tuple[str, str]] = []
_meters_discovered_at = 0.0
_METER_CACHE_TTL = 24 * 60 * 60


@dataclass
class PricedEnergy:
    """Delivered energy priced in integer currency-minor units."""

    intervals: list[dict] = field(default_factory=list)
    cost_minor: Optional[int] = None
    coverage: float = 0.0
    energy_wh: int = 0
    cost_method: str = "actual_agile"


def is_enabled() -> bool:
    """True when an Octopus product code and region are configured."""
    return bool(config.OCTOPUS_PRODUCT_CODE and config.OCTOPUS_REGION)


def is_intelligent_go() -> bool:
    """True when the configured import product is Intelligent Octopus Go."""
    return config.OCTOPUS_PRODUCT_CODE.strip().upper().startswith("INTELLI-")


def consumption_is_enabled() -> bool:
    """True when an Octopus account (API key + number) is configured.

    Separate from :func:`is_enabled`: tariff rates use the public API, while
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
        logger.warning("Failed to fetch Octopus tariff rates", exc_info=True)
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
    """Cost (£) of the allocated Ohme charge ``slots`` against Octopus ``rates``.

    Intelligent Go bills every Ohme smart-charge slot at the cheaper tariff rate,
    including slots scheduled outside the normal overnight window. Other tariffs
    (notably Agile) are priced by time window: energy is assumed drawn at constant
    power across a slot, so the portion in a rate window is
    ``energy × overlap / slot_duration``. Returns None when there is insufficient
    rate evidence to price the complete plan.
    """
    if not slots or not rates:
        return None

    if is_intelligent_go():
        prices = [
            Decimal(str(rate.get("pricePerKwh")))
            for rate in rates
            if isinstance(rate.get("pricePerKwh"), (int, float))
        ]
        if not prices:
            return None
        cheap_rate = min(prices)
        total_energy = Decimal("0")
        for slot in slots:
            if (slot.end - slot.start).total_seconds() > 0:
                total_energy += Decimal(str(slot.energy))
        return float(
            (total_energy * cheap_rate).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
        )

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


def _slot_windows(slots: Optional[list]) -> list[tuple[datetime.datetime, datetime.datetime]]:
    """Return valid aware start/end pairs from Ohme objects or persisted rows."""
    windows = []
    for slot in slots or []:
        if isinstance(slot, dict):
            start = _parse(slot.get("start"))
            end = _parse(slot.get("end"))
        else:
            start = getattr(slot, "start", None)
            end = getattr(slot, "end", None)
        if isinstance(start, datetime.datetime) and isinstance(end, datetime.datetime) and end > start:
            windows.append((start, end))
    return windows


def price_energy_buckets(
    car_by_slot: dict[str, float],
    rates: Optional[list[dict]],
    *,
    smart_slots: Optional[list] = None,
) -> PricedEnergy:
    """Price measured half-hour energy buckets against tariff windows.

    Monetary arithmetic is Decimal throughout and converted to integer minor
    units (pence for GBP) only at the persistence boundary. A session gets an
    actual total only when every delivered Wh is covered exactly once.
    """
    intelligent_go = is_intelligent_go()
    result = PricedEnergy(
        cost_method="actual_intelligent_go" if intelligent_go else "actual_agile"
    )
    windows: list[tuple[datetime.datetime, datetime.datetime, Decimal]] = []
    for rate in rates or []:
        start = _parse(rate.get("from"))
        end = _parse(rate.get("to"))
        price = rate.get("pricePerKwh")
        if start and end and end > start and isinstance(price, (int, float)):
            windows.append((start, end, Decimal(str(price)) * Decimal(100)))
    windows.sort(key=lambda window: window[0])
    cheap_rate = min((window[2] for window in windows), default=None)
    intelligent_slots = _slot_windows(smart_slots) if intelligent_go else []

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
        is_smart_charge = any(
            min(end, slot_end) > max(start, slot_start)
            for slot_start, slot_end in intelligent_slots
        )
        if is_smart_charge and cheap_rate is not None:
            # Octopus bills an Ohme-managed Intelligent Go slot at the off-peak
            # rate even when its clock time falls in a peak tariff window.
            covered_seconds = span
            bucket_cost = energy_kwh * cheap_rate
            weighted_rate = cheap_rate
        else:
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


async def _discover_meters() -> Optional[list[tuple[str, str]]]:
    """Return all current-property import meter identities, refreshed daily."""
    global _meters, _meters_discovered_at
    now = time.monotonic()
    if _meters and now - _meters_discovered_at < _METER_CACHE_TTL:
        return list(_meters)
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
        discovered: list[tuple[str, str]] = []
        for prop in data.get("properties") or []:
            if prop.get("moved_out_at"):
                continue
            for point in prop.get("electricity_meter_points") or []:
                # Skip export (solar feed-in) meter points — we want grid import.
                if point.get("is_export"):
                    continue
                mpan = point.get("mpan")
                for meter in point.get("meters") or []:
                    serial = meter.get("serial_number")
                    identity = (mpan, serial)
                    if mpan and serial and identity not in discovered:
                        discovered.append(identity)
        if discovered:
            _meters = discovered
            _meters_discovered_at = now
            logger.info("Discovered %s Octopus import meter serial(s)", len(discovered))
            return list(discovered)
    except Exception:
        logger.warning("Failed to discover Octopus meter", exc_info=True)
        return None
    logger.warning("No electricity import meters found on the current Octopus property")
    return None


async def fetch_consumption(
    period_from: datetime.datetime, period_to: datetime.datetime
) -> Optional[list[dict]]:
    """Half-hourly household grid import between ``period_from`` and ``period_to``.

    Returns ``[{from, to, importKwh}]`` chronological, following Octopus's
    pagination. None when disabled, the meter can't be discovered, or on any
    failure (so the energy-usage feature degrades to off, like the tariff card).
    """
    global _meters_discovered_at
    if not consumption_is_enabled():
        return None
    meters = await _discover_meters()
    if not meters:
        return None
    headers = _auth_headers()
    timeout = aiohttp.ClientTimeout(total=15)
    by_start: dict[str, dict] = {}
    try:
        async with aiohttp.ClientSession(timeout=timeout) as session:
            for mpan, serial in meters:
                url: Optional[str] = (
                    f"{_BASE}/electricity-meter-points/{mpan}/meters/{serial}/consumption/"
                )
                params: Optional[dict] = {
                    "period_from": period_from.isoformat(),
                    "period_to": period_to.isoformat(),
                    "order_by": "period",
                    "page_size": 25000,
                }
                while url:
                    async with session.get(url, params=params, headers=headers) as resp:
                        if resp.status == 404:
                            # Metadata can change between discovery and reading.
                            # Retry discovery next cycle but preserve other serials.
                            _meters_discovered_at = 0.0
                            logger.warning("Octopus meter %s/%s is no longer readable", mpan, serial)
                            break
                        if resp.status != 200:
                            logger.warning("Octopus consumption API returned HTTP %s", resp.status)
                            return None
                        data = await resp.json()
                    for row in data.get("results") or []:
                        start = row.get("interval_start")
                        end = row.get("interval_end")
                        kwh = row.get("consumption")
                        if start and isinstance(kwh, (int, float)):
                            existing = by_start.get(start)
                            prior = existing["importKwh"] if existing else 0.0
                            by_start[start] = {
                                "from": start,
                                "to": end,
                                "importKwh": round(prior + float(kwh), 6),
                            }
                    url = data.get("next")
                    params = None
    except Exception:
        logger.warning("Failed to fetch Octopus consumption", exc_info=True)
        return None

    return sorted(by_start.values(), key=lambda row: row["from"])
