"""Optional Postgres persistence for charging history (for Grafana).

Enabled only when ``DATABASE_URL`` is set. When it is unset — or the database is
unreachable at startup — every function here is a no-op, so the app behaves
exactly as it did before. This mirrors the graceful-degradation pattern already
used for ntfy (``ntfy.send``) and the settings file: an optional feature must
never be able to break the core charging automation.

All writes are best-effort. A failed write logs a warning and is swallowed so a
transient DB hiccup can never interrupt a charging session. The poll loop writes
a telemetry row every interval; ``main.handle_plugin_event`` records one
charge-session row (plus its schedule) per plug-in; and the statistics endpoint
upserts Ohme's daily totals.
"""

from __future__ import annotations

import asyncio
import datetime
import logging
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from typing import Any, Optional

from alembic import command
from alembic.config import Config
from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

import config

logger = logging.getLogger(__name__)

# Created in init() when DATABASE_URL is set and reachable; stays None otherwise,
# which is the signal every write helper checks to decide whether it is a no-op.
_pool: Optional[AsyncConnectionPool] = None


def _minor_factor(currency: Optional[str]) -> int:
    return {"JPY": 1, "KWD": 1000}.get((currency or "GBP").upper(), 100)


def is_enabled() -> bool:
    """True when history persistence is configured (``DATABASE_URL`` set)."""
    return bool(config.DATABASE_URL)


def is_available() -> bool:
    """True only when Postgres was configured *and* initialised successfully."""
    return _pool is not None


def _run_migrations() -> None:
    """Upgrade the configured database to the repository's latest schema."""
    cfg = Config()
    cfg.set_main_option("script_location", str(Path(__file__).with_name("alembic")))
    # Percent signs have interpolation semantics in ConfigParser.
    url = config.DATABASE_URL
    if url.startswith("postgresql://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgresql://")
    elif url.startswith("postgres://"):
        url = "postgresql+psycopg://" + url.removeprefix("postgres://")
    cfg.set_main_option("sqlalchemy.url", url.replace("%", "%%"))
    command.upgrade(cfg, "head")


async def init() -> None:
    """Open the connection pool and create tables. Safe to call when disabled.

    On any failure (bad URL, DB down) we log and leave ``_pool`` as None so the
    app keeps running without persistence rather than failing to start.
    """
    global _pool
    if not is_enabled():
        return
    try:
        # Alembic/SQLAlchemy uses a synchronous connection; keep it off the event
        # loop before opening the application's async psycopg pool.
        await asyncio.to_thread(_run_migrations)
        pool = AsyncConnectionPool(config.DATABASE_URL, min_size=1, max_size=4, open=False)
        await pool.open(wait=True, timeout=10)
        _pool = pool
        logger.info("Postgres history persistence enabled; schema is at Alembic head")
    except Exception:
        logger.warning(
            "Could not initialise Postgres — history persistence disabled for this run",
            exc_info=True,
        )
        _pool = None


async def close() -> None:
    """Close the pool on shutdown. No-op when never opened."""
    global _pool
    if _pool is not None:
        try:
            await _pool.close()
        finally:
            _pool = None


async def record_session(
    *,
    vehicle_name: Optional[str],
    soc_percent: Optional[int],
    target_percent: Optional[int],
    topup_percent: Optional[int],
    action: str,
    odometer_miles: Optional[int] = None,
    soh_percent: Optional[int] = None,
    session_key: Optional[str] = None,
    vehicle_id: Optional[str] = None,
    vin: Optional[str] = None,
    charger_id: Optional[str] = None,
    source_observed_at: Optional[datetime.datetime] = None,
    plugged_in_at: Optional[datetime.datetime] = None,
) -> Optional[int]:
    """Insert one charge-session row and return its id (None when disabled/failed).

    ``action`` is "configured" when Ohme was set up to top up, or
    "skipped_at_target" when the SOC was already at/above the target.
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "INSERT INTO charge_sessions "
                "(vehicle_name, soc_percent, target_percent, topup_percent, action, "
                " odometer_miles, soh_percent, session_key, vehicle_id, vin, charger_id, "
                " source_observed_at, plugged_in_at, quality_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, "
                " COALESCE(%s, now()), 'validated') "
                "ON CONFLICT (session_key) WHERE session_key IS NOT NULL DO UPDATE SET "
                " vehicle_name = EXCLUDED.vehicle_name, soc_percent = EXCLUDED.soc_percent, "
                " target_percent = EXCLUDED.target_percent, topup_percent = EXCLUDED.topup_percent, "
                " action = EXCLUDED.action, odometer_miles = EXCLUDED.odometer_miles, "
                " soh_percent = EXCLUDED.soh_percent, vehicle_id = EXCLUDED.vehicle_id, "
                " vin = EXCLUDED.vin, charger_id = EXCLUDED.charger_id, "
                " source_observed_at = EXCLUDED.source_observed_at, updated_at = now() "
                "RETURNING id",
                (vehicle_name, soc_percent, target_percent, topup_percent, action,
                 odometer_miles, soh_percent, session_key, vehicle_id, vin, charger_id,
                 source_observed_at, plugged_in_at),
            )
            row = await cur.fetchone()
            return row[0] if row else None
    except Exception:
        logger.warning("Failed to record charge session to Postgres", exc_info=True)
        return None


async def close_session(
    session_key: Optional[str],
    *,
    actual_energy_wh: Optional[float],
    end_soc_percent: Optional[int] = None,
    completion_reason: str = "unplugged",
) -> None:
    """Close the durable session identified by ``session_key``. Idempotent."""
    if _pool is None or not session_key:
        return
    energy = round(actual_energy_wh) if actual_energy_wh is not None else None
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "UPDATE charge_sessions SET unplugged_at = COALESCE(unplugged_at, now()), "
                " completed_at = COALESCE(completed_at, now()), end_soc_percent = %s, "
                " actual_energy_wh = COALESCE(%s, actual_energy_wh), "
                " completion_reason = COALESCE(completion_reason, %s), "
                " quality_status = CASE WHEN %s IS NULL THEN 'incomplete' ELSE 'complete' END, "
                " updated_at = now() WHERE session_key = %s",
                (end_soc_percent, energy, completion_reason, energy, session_key),
            )
    except Exception:
        logger.warning("Failed to close charge session in Postgres", exc_info=True)


async def complete_session(
    session_key: Optional[str],
    *,
    actual_energy_wh: float,
    end_soc_percent: Optional[int],
    completion_reason: str = "finished",
) -> None:
    """Record charge completion while the cable may remain connected."""
    if _pool is None or not session_key:
        return
    energy = max(0, round(actual_energy_wh))
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "UPDATE charge_sessions SET completed_at = COALESCE(completed_at, now()), "
                "end_soc_percent = %s, actual_energy_wh = %s, completion_reason = %s, "
                "quality_status = 'complete', updated_at = now() WHERE session_key = %s",
                (end_soc_percent, energy, completion_reason, session_key),
            )
    except Exception:
        logger.warning("Failed to complete charge session in Postgres", exc_info=True)


async def record_session_event(
    session_id: Optional[int], event_type: str, details: Optional[dict[str, Any]] = None
) -> None:
    """Append an immutable lifecycle/control event for a durable session."""
    if _pool is None or session_id is None:
        return
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "INSERT INTO session_events (session_id, event_type, details) VALUES (%s, %s, %s)",
                (session_id, event_type, Jsonb(details or {})),
            )
    except Exception:
        logger.warning("Failed to record charge-session event", exc_info=True)


async def get_session_id_by_key(session_key: Optional[str]) -> Optional[int]:
    """Resolve a persisted active-session key after a process restart."""
    if _pool is None or not session_key:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id FROM charge_sessions WHERE session_key = %s", (session_key,)
            )
            row = await cur.fetchone()
        return row[0] if row else None
    except Exception:
        logger.warning("Failed to resolve active charge session", exc_info=True)
        return None


async def get_recent_sessions(limit: int) -> Optional[list[dict[str, Any]]]:
    """Return the most recent charge sessions, newest first.

    Returns None when persistence is disabled or the read fails, so the API
    can distinguish "history feature unavailable" from "no sessions yet".
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, plugged_in_at, vehicle_name, soc_percent, target_percent, "
                "topup_percent, action, odometer_miles, soh_percent, actual_energy_wh, "
                "actual_cost_minor, cost_currency, cost_method, tariff_coverage, "
                "quality_status, completed_at FROM charge_sessions "
                "ORDER BY plugged_in_at DESC LIMIT %s",
                (limit,),
            )
            rows = await cur.fetchall()
        return [
            {
                "id": row[0],
                "pluggedInAt": row[1].isoformat() if row[1] else None,
                "vehicleName": row[2],
                "socPercent": row[3],
                "targetPercent": row[4],
                "topupPercent": row[5],
                "action": row[6],
                "odometerMiles": row[7],
                "sohPercent": row[8],
                "actualEnergyKwh": round(row[9] / 1000, 3) if row[9] is not None else None,
                "actualCost": round(row[10] / 100, 2) if row[10] is not None else None,
                "costCurrency": row[11],
                "costMethod": row[12],
                "tariffCoverage": row[13],
                "quality": row[14],
                "completedAt": row[15].isoformat() if row[15] else None,
            }
            for row in rows
        ]
    except Exception:
        logger.warning("Failed to read charge sessions from Postgres", exc_info=True)
        return None


async def get_all_sessions() -> Optional[list[dict[str, Any]]]:
    """Return every charge session, oldest first, for a full-history export.

    Same shape as :func:`get_recent_sessions` but unbounded and chronological
    (the natural order for a spreadsheet/analysis). The table holds one row per
    plug-in, so even years of history is a few thousand rows. Returns None when
    persistence is disabled or the read fails, so the API can 404 the export.
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT id, plugged_in_at, vehicle_name, soc_percent, target_percent, "
                "topup_percent, action, odometer_miles, soh_percent, actual_energy_wh, "
                "actual_cost_minor, cost_currency, cost_method, tariff_coverage, "
                "quality_status, completed_at FROM charge_sessions "
                "ORDER BY plugged_in_at ASC"
            )
            rows = await cur.fetchall()
        return [
            {
                "id": row[0],
                "pluggedInAt": row[1].isoformat() if row[1] else None,
                "vehicleName": row[2],
                "socPercent": row[3],
                "targetPercent": row[4],
                "topupPercent": row[5],
                "action": row[6],
                "odometerMiles": row[7],
                "sohPercent": row[8],
                "actualEnergyKwh": round(row[9] / 1000, 3) if row[9] is not None else None,
                "actualCost": round(row[10] / 100, 2) if row[10] is not None else None,
                "costCurrency": row[11],
                "costMethod": row[12],
                "tariffCoverage": row[13],
                "quality": row[14],
                "completedAt": row[15].isoformat() if row[15] else None,
            }
            for row in rows
        ]
    except Exception:
        logger.warning("Failed to read all charge sessions from Postgres", exc_info=True)
        return None


async def get_soh_history(limit: int) -> Optional[list[dict[str, Any]]]:
    """Battery state-of-health readings over time, oldest first, for the trend.

    Captured once per plug-in, SoH moves very slowly, so consecutive identical
    readings are collapsed to one point per *change* — the series stays compact
    and the trend line is meaningful rather than a long flat run. Returns None
    when persistence is disabled or the read fails (mirrors get_recent_sessions
    so the API can hide the card).
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT plugged_in_at, soh_percent FROM charge_sessions "
                "WHERE soh_percent IS NOT NULL "
                "ORDER BY plugged_in_at DESC LIMIT %s",
                (limit,),
            )
            rows = await cur.fetchall()
    except Exception:
        logger.warning("Failed to read SoH history from Postgres", exc_info=True)
        return None
    # rows come newest-first; walk oldest-first and keep only the points where
    # the value changed (plus the very first reading).
    history: list[dict[str, Any]] = []
    prev: Optional[int] = None
    for ts, soh in reversed(rows):
        if soh != prev:
            history.append({"date": ts.isoformat() if ts else None, "sohPercent": soh})
            prev = soh
    return history


async def record_schedule(
    *,
    session_id: Optional[int],
    slots: list[dict[str, Any]],
    next_slot_start: Optional[datetime.datetime],
    next_slot_end: Optional[datetime.datetime],
    reason: str = "initial",
) -> None:
    """Persist the Ohme charge schedule captured when a session was configured."""
    if _pool is None:
        return
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "INSERT INTO schedule_snapshots "
                "(session_id, next_slot_start, next_slot_end, slots, revision, reason) "
                "VALUES (%s, %s, %s, %s, "
                " (SELECT COALESCE(MAX(revision), 0) + 1 FROM schedule_snapshots "
                "  WHERE session_id IS NOT DISTINCT FROM %s), %s)",
                (session_id, next_slot_start, next_slot_end, Jsonb(slots), session_id, reason),
            )
    except Exception:
        logger.warning("Failed to record charge schedule to Postgres", exc_info=True)


async def record_telemetry(snap: Any, *, session_id: Optional[int] = None) -> None:
    """Append one telemetry row from a :class:`state.StatusSnapshot`."""
    if _pool is None:
        return
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "INSERT INTO telemetry "
                "(vehicle_name, battery_percent, charger_status, connected, charger_online, "
                " power_watts, power_amps, power_volts, target_percent, session_energy_wh, "
                " session_id, quality_status) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
                (
                    snap.vehicle_name,
                    snap.battery_percent,
                    snap.charger_status,
                    snap.connected,
                    snap.charger_online,
                    snap.power_watts,
                    snap.power_amps,
                    snap.power_volts,
                    snap.target_percent,
                    snap.session_energy_wh,
                    session_id,
                    "session_linked" if session_id is not None else "unlinked",
                ),
            )
    except Exception:
        logger.warning("Failed to record telemetry to Postgres", exc_info=True)


async def prune_telemetry(retention_days: int) -> None:
    """Delete telemetry rows older than ``retention_days`` (<= 0 keeps forever).

    Called on the daily-stats cadence so the per-poll table doesn't grow
    without bound. Best-effort like every other write here.
    """
    if _pool is None or retention_days <= 0:
        return
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "DELETE FROM telemetry WHERE recorded_at < now() - %s * interval '1 day'",
                (retention_days,),
            )
    except Exception:
        logger.warning("Failed to prune old telemetry from Postgres", exc_info=True)


async def record_daily_stats(daily: list[dict[str, Any]], currency: Optional[str]) -> None:
    """Upsert Ohme's per-day totals (energy/savings/cost) keyed by date.

    ``daily`` is the list produced by :func:`api.parse_summary`. Rows without a
    date are skipped. Re-running for the same dates overwrites them so the latest
    Ohme figures always win.
    """
    if _pool is None or not daily:
        return
    factor = _minor_factor(currency)
    rows = []
    for day in daily:
        if not day.get("date"):
            continue
        energy_kwh = Decimal(str(day.get("energyKwh") or 0))
        savings = Decimal(str(day.get("savings") or 0))
        cost = Decimal(str(day.get("cost") or 0))
        rows.append(
            (
                day["date"], float(energy_kwh), float(savings), float(cost), currency,
                int((energy_kwh * 1000).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                int((savings * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                int((cost * factor).quantize(Decimal("1"), rounding=ROUND_HALF_UP)),
                bool(day.get("isComplete", False)),
            )
        )
    if not rows:
        return
    try:
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO daily_stats "
                    "(stat_date, energy_kwh, savings, cost, currency, energy_wh, "
                    "savings_minor, cost_minor, is_complete) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (stat_date) DO UPDATE SET "
                    "  energy_kwh = EXCLUDED.energy_kwh, "
                    "  savings    = EXCLUDED.savings, "
                    "  cost       = EXCLUDED.cost, "
                    "  currency   = EXCLUDED.currency, "
                    "  energy_wh = EXCLUDED.energy_wh, "
                    "  savings_minor = EXCLUDED.savings_minor, "
                    "  cost_minor = EXCLUDED.cost_minor, "
                    "  is_complete = EXCLUDED.is_complete, "
                    "  updated_at = now()",
                    rows,
                )
    except Exception:
        logger.warning("Failed to record daily stats to Postgres", exc_info=True)


async def get_single_vehicle_id() -> Optional[str]:
    """Return the sole persisted vehicle id, or None when ambiguous/unavailable."""
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT MIN(vehicle_id), COUNT(DISTINCT vehicle_id) FROM charge_sessions "
                "WHERE vehicle_id IS NOT NULL"
            )
            row = await cur.fetchone()
        return row[0] if row and row[1] == 1 else None
    except Exception:
        logger.warning("Failed to resolve persisted vehicle identity", exc_info=True)
        return None


async def get_vehicle_driving_metrics(
    start: datetime.datetime, end: datetime.datetime, vehicle_id: Optional[str]
) -> Optional[dict[str, Any]]:
    """Pair each home-charge session with distance driven before the next plug-in.

    Only intervals fully contained in ``[start, end)`` and carrying a final
    charger energy counter are included. Cost-per-mile uses the stricter subset
    whose session has a reconciled actual cost.
    """
    if _pool is None or not vehicle_id:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT plugged_in_at, odometer_miles, actual_energy_wh, "
                "actual_cost_minor, cost_currency FROM charge_sessions "
                "WHERE vehicle_id = %s AND plugged_in_at >= %s AND plugged_in_at <= %s "
                "ORDER BY plugged_in_at",
                (vehicle_id, start, end),
            )
            rows = await cur.fetchall()
    except Exception:
        logger.warning("Failed to read vehicle driving intervals", exc_info=True)
        return None

    energy_miles = energy_wh = interval_count = 0
    cost_miles = cost_minor = cost_interval_count = 0
    cost_currency: Optional[str] = None
    first_at = last_at = None
    for current, nxt in zip(rows, rows[1:]):
        at, odometer, session_wh, session_cost, currency = current
        next_at, next_odometer = nxt[0], nxt[1]
        if at is None or next_at is None or at < start or next_at > end:
            continue
        if odometer is None or next_odometer is None or next_odometer <= odometer:
            continue
        if session_wh is None or session_wh <= 0:
            continue
        miles = next_odometer - odometer
        energy_miles += miles
        energy_wh += session_wh
        interval_count += 1
        first_at = first_at or at
        last_at = next_at
        if session_cost is not None and currency:
            if cost_currency is None:
                cost_currency = currency
            if currency == cost_currency:
                cost_miles += miles
                cost_minor += session_cost
                cost_interval_count += 1
    if interval_count == 0:
        return None
    return {
        "vehicleId": vehicle_id,
        "milesDriven": energy_miles,
        "energyWh": energy_wh,
        "intervalCount": interval_count,
        "from": first_at,
        "to": last_at,
        "costMilesDriven": cost_miles,
        "costMinor": cost_minor if cost_interval_count else None,
        "costIntervalCount": cost_interval_count,
        "costCurrency": cost_currency if cost_interval_count else None,
    }


async def get_telemetry_between(
    start: datetime.datetime, end: datetime.datetime
) -> Optional[list[tuple]]:
    """Ordered session-linked telemetry rows in ``[start, end]``.

    Feeds :func:`energy.attribute_car_kwh` so the car's half-hourly share can be
    reconstructed from the cumulative session energy. The window is widened by the
    caller so the first slot's delta has a preceding reading. None when disabled
    or the read fails.
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT recorded_at, session_id, session_energy_wh, power_watts, "
                "charger_status, connected FROM telemetry "
                "WHERE recorded_at >= %s AND recorded_at <= %s "
                "ORDER BY recorded_at",
                (start, end),
            )
            rows = await cur.fetchall()
        return [tuple(row) for row in rows]
    except Exception:
        logger.warning("Failed to read telemetry from Postgres", exc_info=True)
        return None


async def get_session_attribution_rows(session_id: int) -> Optional[list[tuple]]:
    """Raw counter/power rows for one explicit session, oldest first."""
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT recorded_at, session_id, session_energy_wh, power_watts, "
                "charger_status, connected FROM telemetry "
                "WHERE session_id = %s ORDER BY recorded_at",
                (session_id,),
            )
            return [tuple(row) for row in await cur.fetchall()]
    except Exception:
        logger.warning("Failed to read session attribution telemetry", exc_info=True)
        return None


async def upsert_tariff_rates(rates: list[dict[str, Any]]) -> None:
    """Persist normalized tariff windows so actual cost is dashboard-independent."""
    if _pool is None or not rates:
        return
    source = f"octopus_agile:{config.OCTOPUS_PRODUCT_CODE}:{config.OCTOPUS_REGION}"
    params = []
    for rate in rates:
        if not rate.get("from") or not rate.get("to"):
            continue
        try:
            price_minor = Decimal(str(rate["pricePerKwh"])) * 100
        except (KeyError, ValueError, TypeError):
            continue
        params.append((rate["from"], rate["to"], price_minor, "GBP", source))
    if not params:
        return
    try:
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO tariff_rates "
                    "(valid_from, valid_to, price_minor_per_kwh, currency, source) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (valid_from, source) DO UPDATE SET "
                    "valid_to = EXCLUDED.valid_to, "
                    "price_minor_per_kwh = EXCLUDED.price_minor_per_kwh, "
                    "currency = EXCLUDED.currency, ingested_at = now()",
                    params,
                )
    except Exception:
        logger.warning("Failed to persist tariff rates", exc_info=True)


async def get_tariff_rates(
    start: datetime.datetime, end: datetime.datetime
) -> Optional[list[dict[str, Any]]]:
    """Persisted tariff windows overlapping ``[start, end)``."""
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT valid_from, valid_to, price_minor_per_kwh, currency, source "
                "FROM tariff_rates WHERE valid_to > %s AND valid_from < %s "
                "ORDER BY valid_from",
                (start, end),
            )
            rows = await cur.fetchall()
        return [
            {
                "from": row[0].isoformat(),
                "to": row[1].isoformat(),
                "pricePerKwh": float(row[2] / 100),
                "currency": row[3],
                "source": row[4],
            }
            for row in rows
        ]
    except Exception:
        logger.warning("Failed to read persisted tariff rates", exc_info=True)
        return None


async def record_session_reconciliation(
    session_id: Optional[int], priced: Any, *, counter_energy_wh: float
) -> None:
    """Persist tariff-bucket energy and the reconciled actual session cost."""
    if _pool is None or session_id is None:
        return
    counter_wh = max(0, round(counter_energy_wh))
    delta_wh = counter_wh - priced.energy_wh
    tolerance_wh = max(100, round(counter_wh * 0.02))
    if priced.coverage < 1:
        quality = "tariff_incomplete"
    elif abs(delta_wh) > tolerance_wh:
        quality = "energy_mismatch"
    else:
        quality = "reconciled"
    interval_params = [
        (
            session_id, interval["start"], interval["end"], interval["energyWh"],
            interval["costMinor"], interval["rateMinorPerKwh"], interval["currency"],
            interval["quality"],
        )
        for interval in priced.intervals
    ]
    try:
        async with _pool.connection() as conn:
            if interval_params:
                async with conn.cursor() as cur:
                    await cur.executemany(
                        "INSERT INTO charging_intervals "
                        "(session_id, interval_start, interval_end, energy_wh, cost_minor, "
                        "rate_minor_per_kwh, currency, quality_status) "
                        "VALUES (%s, %s, %s, %s, %s, %s, %s, %s) "
                        "ON CONFLICT (session_id, interval_start) DO UPDATE SET "
                        "interval_end = EXCLUDED.interval_end, energy_wh = EXCLUDED.energy_wh, "
                        "cost_minor = EXCLUDED.cost_minor, "
                        "rate_minor_per_kwh = EXCLUDED.rate_minor_per_kwh, "
                        "currency = EXCLUDED.currency, quality_status = EXCLUDED.quality_status, "
                        "updated_at = now()",
                        interval_params,
                    )
            stored_cost_minor = priced.cost_minor if quality == "reconciled" else None
            await conn.execute(
                "UPDATE charge_sessions SET actual_cost_minor = %s, cost_currency = %s, "
                "cost_method = %s, tariff_coverage = %s, reconstructed_energy_wh = %s, "
                "reconciliation_delta_wh = %s, quality_status = %s, updated_at = now() "
                "WHERE id = %s",
                (
                    stored_cost_minor,
                    "GBP" if stored_cost_minor is not None else None,
                    "actual_agile" if stored_cost_minor is not None else None,
                    priced.coverage,
                    priced.energy_wh,
                    delta_wh,
                    quality,
                    session_id,
                ),
            )
    except Exception:
        logger.warning("Failed to persist session reconciliation", exc_info=True)


async def get_session_telemetry(session_id: int) -> Optional[list[dict[str, Any]]]:
    """Per-poll telemetry for one session's charge curve, oldest first.

    Rows are selected by their explicit ``telemetry.session_id`` foreign key;
    timestamps are never used to infer a boundary. Each point carries the SOC,
    draw and cumulative session energy at that poll. Returns None when persistence
    is off, the read fails, or the session id is unknown.
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute("SELECT id FROM charge_sessions WHERE id = %s", (session_id,))
            row = await cur.fetchone()
            if row is None:
                return None
            cur = await conn.execute(
                "SELECT recorded_at, battery_percent, power_watts, session_energy_wh "
                "FROM telemetry WHERE session_id = %s ORDER BY recorded_at", (session_id,)
            )
            rows = await cur.fetchall()
        return [
            {
                "at": r[0].isoformat() if r[0] else None,
                "socPercent": r[1],
                "powerWatts": r[2],
                "sessionEnergyKwh": round(r[3] / 1000, 2) if r[3] is not None else None,
            }
            for r in rows
        ]
    except Exception:
        logger.warning("Failed to read session telemetry from Postgres", exc_info=True)
        return None


async def upsert_grid_consumption(rows: list[dict[str, Any]]) -> None:
    """Upsert half-hourly grid-import rows keyed by ``start`` (interval start).

    ``rows`` is the list from :func:`energy.merge_usage`
    (``{start, end, importKwh, carKwh, houseKwh}``). Idempotent so re-ingesting a
    window refreshes late-arriving Octopus data. Best-effort like every write here.
    """
    if _pool is None or not rows:
        return
    params = [
        (
            r["start"], r.get("end"), r.get("importKwh"), r.get("carKwh"),
            r.get("houseKwh"), r.get("unattributedKwh", 0), r.get("quality", "unknown"),
        )
        for r in rows
        if r.get("start")
    ]
    if not params:
        return
    try:
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO grid_consumption "
                    "(interval_start, interval_end, import_kwh, car_kwh, house_kwh, "
                    "unattributed_kwh, quality_status) "
                    "VALUES (%s, %s, %s, %s, %s, %s, %s) "
                    "ON CONFLICT (interval_start) DO UPDATE SET "
                    "  interval_end = EXCLUDED.interval_end, "
                    "  import_kwh   = EXCLUDED.import_kwh, "
                    "  car_kwh      = EXCLUDED.car_kwh, "
                    "  house_kwh    = EXCLUDED.house_kwh, "
                    "  unattributed_kwh = EXCLUDED.unattributed_kwh, "
                    "  quality_status = EXCLUDED.quality_status, "
                    "  updated_at   = now()",
                    params,
                )
    except Exception:
        logger.warning("Failed to upsert grid consumption to Postgres", exc_info=True)


async def get_grid_consumption(
    start: datetime.datetime, end: datetime.datetime
) -> Optional[list[dict[str, Any]]]:
    """Half-hourly grid-import rows in ``[start, end)``, chronological.

    Returns None when persistence is disabled or the read fails, so the API can
    report the energy-usage feature as unavailable (hiding the card).
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT interval_start, interval_end, import_kwh, car_kwh, house_kwh, "
                "unattributed_kwh, quality_status "
                "FROM grid_consumption "
                "WHERE interval_start >= %s AND interval_start < %s "
                "ORDER BY interval_start",
                (start, end),
            )
            rows = await cur.fetchall()
        return [
            {
                "start": row[0].isoformat() if row[0] else None,
                "end": row[1].isoformat() if row[1] else None,
                "importKwh": row[2],
                "carKwh": row[3],
                "houseKwh": row[4],
                "unattributedKwh": row[5],
                "quality": row[6],
            }
            for row in rows
        ]
    except Exception:
        logger.warning("Failed to read grid consumption from Postgres", exc_info=True)
        return None
