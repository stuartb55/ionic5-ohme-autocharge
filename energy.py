"""Pure helpers for the household-vs-car energy breakdown.

The whole-house grid import comes from Octopus (:mod:`octopus.fetch_consumption`);
the car's share is reconstructed here from the charge telemetry the poll loop
already records. Keeping the maths pure (no I/O) makes it straightforward to unit
test the slot attribution and the import/car/house merge in isolation.
"""

from __future__ import annotations

import datetime
from typing import Optional

# Octopus consumption is reported on half-hour boundaries (:00 and :30), so the
# car share is bucketed onto the same grid to line the two series up.
_SLOT_SECONDS = 30 * 60


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


def attribute_car_kwh(telemetry_rows: list) -> dict[str, float]:
    """Car energy per half-hour slot, keyed by canonical UTC slot-start ISO.

    ``telemetry_rows`` is an ordered sequence of ``(recorded_at, session_energy_wh)``
    where ``session_energy_wh`` is the cumulative energy of the *current* charge
    session (it resets to ~0 when a new session starts). The energy added between
    two consecutive readings is their positive delta; a negative delta means a new
    session began, so the later reading is the energy-since-reset. Each delta is
    spread uniformly over the time between the two readings and apportioned to the
    half-hour slots it overlaps — the same proportional split used by
    :func:`octopus.cost_for_slots`.
    """
    rows: list[tuple[datetime.datetime, float]] = []
    for recorded_at, energy_wh in telemetry_rows:
        dt = _parse(recorded_at)
        if dt is not None and energy_wh is not None:
            rows.append((dt, float(energy_wh)))
    rows.sort(key=lambda r: r[0])

    buckets: dict[str, float] = {}
    for (t0, e0), (t1, e1) in zip(rows, rows[1:]):
        span = (t1 - t0).total_seconds()
        if span <= 0:
            continue
        delta_wh = e1 - e0
        if delta_wh < 0:  # session reset between readings → energy from zero
            delta_wh = max(0.0, e1)
        if delta_wh <= 0:
            continue
        # Walk the half-hour slots the [t0, t1] interval overlaps.
        w_start = _slot_floor(t0)
        while w_start < t1:
            w_end = w_start + datetime.timedelta(seconds=_SLOT_SECONDS)
            overlap = (min(t1, w_end) - max(t0, w_start)).total_seconds()
            if overlap > 0:
                key = w_start.isoformat()
                buckets[key] = buckets.get(key, 0.0) + (delta_wh / 1000) * (overlap / span)
            w_start = w_end
    return buckets


def merge_usage(import_rows: list, car_by_slot: dict[str, float]) -> list[dict]:
    """Combine whole-house import with the per-slot car share.

    ``import_rows`` is ``[{from, to, importKwh}]`` from
    :func:`octopus.fetch_consumption`; ``car_by_slot`` is the output of
    :func:`attribute_car_kwh`. Returns ``[{start, end, importKwh, carKwh,
    houseKwh}]`` chronological, where ``houseKwh = max(0, importKwh − carKwh)``
    (the clamp absorbs minor timing skew between the two data sources so the
    rest-of-house figure never goes negative).
    """
    out: list[dict] = []
    for row in import_rows:
        key = _canon(row.get("from"))
        import_kwh = float(row.get("importKwh") or 0.0)
        car_kwh = round(car_by_slot.get(key, 0.0), 4) if key else 0.0
        # Never attribute more to the car than the meter saw for the slot.
        car_kwh = min(car_kwh, round(import_kwh, 4))
        out.append(
            {
                "start": row.get("from"),
                "end": row.get("to"),
                "importKwh": round(import_kwh, 4),
                "carKwh": car_kwh,
                "houseKwh": round(max(0.0, import_kwh - car_kwh), 4),
            }
        )
    out.sort(key=lambda r: r["start"] or "")
    return out
