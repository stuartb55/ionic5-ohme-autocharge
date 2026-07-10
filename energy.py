"""Pure helpers for the household-vs-car energy breakdown.

The whole-house grid import comes from Octopus (:mod:`octopus.fetch_consumption`);
the car's share is reconstructed here from the charge telemetry the poll loop
already records. Keeping the maths pure (no I/O) makes it straightforward to unit
test the slot attribution and the import/car/house merge in isolation.
"""

from __future__ import annotations

import datetime
from dataclasses import dataclass, field
from typing import Optional

# Octopus consumption is reported on half-hour boundaries (:00 and :30), so the
# car share is bucketed onto the same grid to line the two series up.
_SLOT_SECONDS = 30 * 60


@dataclass
class EnergyAttribution:
    """Confident car energy plus slots that cannot be split accurately."""

    car_by_slot: dict[str, float] = field(default_factory=dict)
    uncertain_slots: set[str] = field(default_factory=set)
    issue_count: int = 0


def _parse(ts) -> Optional[datetime.datetime]:
    """Parse an ISO timestamp (or pass through a datetime) to an aware UTC datetime."""
    if isinstance(ts, datetime.datetime):
        dt = ts
    else:
        try:
            dt = datetime.datetime.fromisoformat(str(ts).replace("Z", "+00:00"))
        except (ValueError, AttributeError):
            return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=datetime.timezone.utc)
    return dt.astimezone(datetime.timezone.utc)


def _canon(ts) -> Optional[str]:
    """Canonical UTC ISO key for a half-hour boundary, so the car buckets and the
    Octopus import rows agree on the same key regardless of source offset/format."""
    dt = _parse(ts)
    return dt.isoformat() if dt is not None else None


def _slot_floor(dt: datetime.datetime) -> datetime.datetime:
    """Floor a UTC datetime to its containing half-hour boundary."""
    minute = 0 if dt.minute < 30 else 30
    return dt.replace(minute=minute, second=0, microsecond=0)


def _overlapping_slot_keys(
    start: datetime.datetime, end: datetime.datetime
) -> set[str]:
    keys: set[str] = set()
    slot = _slot_floor(start)
    while slot < end:
        keys.add(slot.isoformat())
        slot += datetime.timedelta(seconds=_SLOT_SECONDS)
    return keys


def attribute_car_kwh(
    telemetry_rows: list,
    *,
    max_gap_seconds: int = 15 * 60,
    max_power_watts: float = 25_000,
) -> EnergyAttribution:
    """Car energy per half-hour slot, keyed by canonical UTC slot-start ISO.

    Rows are ``(recorded_at, session_id, session_energy_wh, power_watts,
    charger_status, connected)``. Deltas are accepted only inside one explicit
    session, over a bounded sample gap, with a plausible magnitude. Intervals
    that fail those checks are marked uncertain rather than spread across time.
    """
    rows: list[tuple[datetime.datetime, int, float, float, str, bool]] = []
    for row in telemetry_rows:
        if len(row) < 6:
            continue  # legacy unlinked rows cannot be attributed safely
        recorded_at, session_id, energy_wh, power_watts, status, connected = row[:6]
        dt = _parse(recorded_at)
        if dt is not None and session_id is not None and energy_wh is not None:
            rows.append(
                (dt, int(session_id), float(energy_wh), float(power_watts or 0), str(status), bool(connected))
            )
    rows.sort(key=lambda r: r[0])

    result = EnergyAttribution()
    seen_sessions: set[int] = set()
    for recorded_at, session_id, energy_wh, *_ in rows:
        if session_id not in seen_sessions:
            seen_sessions.add(session_id)
            if energy_wh > 0:
                # No zero/baseline sample exists for the energy delivered before
                # this first row, so the containing meter slot cannot be split.
                result.uncertain_slots.add(_slot_floor(recorded_at).isoformat())
                result.issue_count += 1
    for (t0, sid0, e0, p0, status0, connected0), (
        t1, sid1, e1, p1, status1, connected1,
    ) in zip(rows, rows[1:]):
        if sid0 != sid1:
            continue
        span = (t1 - t0).total_seconds()
        if span <= 0:
            continue
        delta_wh = e1 - e0
        if delta_wh == 0:
            continue
        plausible_wh = max_power_watts * span / 3600 * 1.25 + 100
        trustworthy = (
            delta_wh > 0
            and span <= max_gap_seconds
            and delta_wh <= plausible_wh
            and connected0
            and connected1
            and status0 != "unplugged"
            and status1 != "unplugged"
        )
        if not trustworthy:
            result.uncertain_slots.update(_overlapping_slot_keys(t0, t1))
            result.issue_count += 1
            continue
        if delta_wh <= 0:
            continue
        # Walk the half-hour slots the [t0, t1] interval overlaps.
        w_start = _slot_floor(t0)
        while w_start < t1:
            w_end = w_start + datetime.timedelta(seconds=_SLOT_SECONDS)
            overlap = (min(t1, w_end) - max(t0, w_start)).total_seconds()
            if overlap > 0:
                key = w_start.isoformat()
                result.car_by_slot[key] = (
                    result.car_by_slot.get(key, 0.0) + (delta_wh / 1000) * (overlap / span)
                )
            w_start = w_end
    return result


def merge_usage(
    import_rows: list, attribution: EnergyAttribution | dict[str, float]
) -> list[dict]:
    """Combine whole-house import with the per-slot car share.

    Uncertain or materially inconsistent slots are not guessed: their metered
    import is reported as ``unattributedKwh`` and both component estimates are
    zero. This preserves ``import = car + house + unattributed``.
    """
    if isinstance(attribution, dict):
        attribution = EnergyAttribution(car_by_slot=attribution)
    out: list[dict] = []
    for row in import_rows:
        key = _canon(row.get("from"))
        import_kwh = float(row.get("importKwh") or 0.0)
        import_kwh = round(max(0.0, import_kwh), 4)
        estimated_car = round(attribution.car_by_slot.get(key, 0.0), 4) if key else 0.0
        uncertain = key in attribution.uncertain_slots if key else False
        if uncertain or estimated_car > import_kwh + 0.05:
            car_kwh = house_kwh = 0.0
            unattributed_kwh = import_kwh
            quality = "uncertain_gap" if uncertain else "inconsistent"
        else:
            car_kwh = min(estimated_car, import_kwh)
            house_kwh = round(import_kwh - car_kwh, 4)
            unattributed_kwh = 0.0
            quality = "timing_adjusted" if estimated_car > import_kwh else "good"
        out.append(
            {
                "start": row.get("from"),
                "end": row.get("to"),
                "importKwh": import_kwh,
                "carKwh": car_kwh,
                "houseKwh": house_kwh,
                "unattributedKwh": unattributed_kwh,
                "quality": quality,
            }
        )
    out.sort(key=lambda r: r["start"] or "")
    return out
