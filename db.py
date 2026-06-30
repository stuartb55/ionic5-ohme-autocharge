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

import datetime
import logging
from typing import Any, Optional

from psycopg.types.json import Jsonb
from psycopg_pool import AsyncConnectionPool

import config

logger = logging.getLogger(__name__)

# Created in init() when DATABASE_URL is set and reachable; stays None otherwise,
# which is the signal every write helper checks to decide whether it is a no-op.
_pool: Optional[AsyncConnectionPool] = None

# Schema is idempotent (IF NOT EXISTS) so init() can run on every startup. psycopg
# sends one statement per execute() with the extended protocol, so keep these as
# separate statements rather than one multi-statement string.
_SCHEMA: tuple[str, ...] = (
    """
    CREATE TABLE IF NOT EXISTS charge_sessions (
        id              BIGSERIAL PRIMARY KEY,
        plugged_in_at   TIMESTAMPTZ NOT NULL DEFAULT now(),
        vehicle_name    TEXT,
        soc_percent     INTEGER,
        target_percent  INTEGER,
        topup_percent   INTEGER,
        action          TEXT
    )
    """,
    # Added after the initial release; ALTER keeps existing databases in step.
    # The odometer (miles) at plug-in lets us derive driving efficiency (mi/kWh)
    # from the distance between consecutive sessions and the energy charged.
    "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS odometer_miles INTEGER",
    # Battery state of health (%) at plug-in, for a degradation trend over time.
    "ALTER TABLE charge_sessions ADD COLUMN IF NOT EXISTS soh_percent INTEGER",
    """
    CREATE TABLE IF NOT EXISTS schedule_snapshots (
        id               BIGSERIAL PRIMARY KEY,
        session_id       BIGINT REFERENCES charge_sessions(id) ON DELETE CASCADE,
        recorded_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
        next_slot_start  TIMESTAMPTZ,
        next_slot_end    TIMESTAMPTZ,
        slots            JSONB
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS telemetry (
        recorded_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
        vehicle_name       TEXT,
        battery_percent    INTEGER,
        charger_status     TEXT,
        connected          BOOLEAN,
        charger_online     BOOLEAN,
        power_watts        DOUBLE PRECISION,
        power_amps         DOUBLE PRECISION,
        power_volts        INTEGER,
        target_percent     INTEGER,
        session_energy_wh  DOUBLE PRECISION
    )
    """,
    "CREATE INDEX IF NOT EXISTS telemetry_recorded_at_idx ON telemetry (recorded_at)",
    """
    CREATE TABLE IF NOT EXISTS daily_stats (
        stat_date    DATE PRIMARY KEY,
        energy_kwh   DOUBLE PRECISION,
        savings      DOUBLE PRECISION,
        cost         DOUBLE PRECISION,
        currency     TEXT,
        updated_at   TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
    # Half-hourly whole-house grid import (from Octopus) with the car share
    # (reconstructed from telemetry) and the remaining household usage broken out,
    # so Grafana can chart car-vs-house directly. See docs/grafana.md.
    """
    CREATE TABLE IF NOT EXISTS grid_consumption (
        interval_start TIMESTAMPTZ PRIMARY KEY,
        interval_end   TIMESTAMPTZ,
        import_kwh     DOUBLE PRECISION,
        car_kwh        DOUBLE PRECISION,
        house_kwh      DOUBLE PRECISION,
        updated_at     TIMESTAMPTZ NOT NULL DEFAULT now()
    )
    """,
)


def is_enabled() -> bool:
    """True when history persistence is configured (``DATABASE_URL`` set)."""
    return bool(config.DATABASE_URL)


async def init() -> None:
    """Open the connection pool and create tables. Safe to call when disabled.

    On any failure (bad URL, DB down) we log and leave ``_pool`` as None so the
    app keeps running without persistence rather than failing to start.
    """
    global _pool
    if not is_enabled():
        return
    try:
        pool = AsyncConnectionPool(config.DATABASE_URL, min_size=1, max_size=4, open=False)
        await pool.open(wait=True, timeout=10)
        async with pool.connection() as conn:
            for statement in _SCHEMA:
                await conn.execute(statement)
        _pool = pool
        logger.info("Postgres history persistence enabled")
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
                " odometer_miles, soh_percent) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s) RETURNING id",
                (vehicle_name, soc_percent, target_percent, topup_percent, action,
                 odometer_miles, soh_percent),
            )
            row = await cur.fetchone()
            return row[0] if row else None
    except Exception:
        logger.warning("Failed to record charge session to Postgres", exc_info=True)
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
                "topup_percent, action, odometer_miles, soh_percent FROM charge_sessions "
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
                "topup_percent, action, odometer_miles, soh_percent FROM charge_sessions "
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


async def get_miles_driven(since: datetime.datetime) -> Optional[int]:
    """Miles driven since ``since``, from the odometer span across charge sessions.

    Returns the difference between the highest and lowest odometer reading among
    sessions plugged in on/after ``since``. None when persistence is disabled,
    the read fails, or there aren't at least two odometer readings to span (so
    we never report a bogus "0 miles driven" from a single data point).
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT MAX(odometer_miles) - MIN(odometer_miles) FROM charge_sessions "
                "WHERE plugged_in_at >= %s AND odometer_miles IS NOT NULL "
                "HAVING COUNT(odometer_miles) >= 2",
                (since,),
            )
            row = await cur.fetchone()
        return row[0] if row else None
    except Exception:
        logger.warning("Failed to read odometer span from Postgres", exc_info=True)
        return None


async def record_schedule(
    *,
    session_id: Optional[int],
    slots: list[dict[str, Any]],
    next_slot_start: Optional[datetime.datetime],
    next_slot_end: Optional[datetime.datetime],
) -> None:
    """Persist the Ohme charge schedule captured when a session was configured."""
    if _pool is None:
        return
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "INSERT INTO schedule_snapshots "
                "(session_id, next_slot_start, next_slot_end, slots) "
                "VALUES (%s, %s, %s, %s)",
                (session_id, next_slot_start, next_slot_end, Jsonb(slots)),
            )
    except Exception:
        logger.warning("Failed to record charge schedule to Postgres", exc_info=True)


async def record_telemetry(snap: Any) -> None:
    """Append one telemetry row from a :class:`state.StatusSnapshot`."""
    if _pool is None:
        return
    try:
        async with _pool.connection() as conn:
            await conn.execute(
                "INSERT INTO telemetry "
                "(vehicle_name, battery_percent, charger_status, connected, charger_online, "
                " power_watts, power_amps, power_volts, target_percent, session_energy_wh) "
                "VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
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
    rows = [
        (day["date"], day.get("energyKwh"), day.get("savings"), day.get("cost"), currency)
        for day in daily
        if day.get("date")
    ]
    if not rows:
        return
    try:
        async with _pool.connection() as conn:
            async with conn.cursor() as cur:
                await cur.executemany(
                    "INSERT INTO daily_stats "
                    "(stat_date, energy_kwh, savings, cost, currency) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (stat_date) DO UPDATE SET "
                    "  energy_kwh = EXCLUDED.energy_kwh, "
                    "  savings    = EXCLUDED.savings, "
                    "  cost       = EXCLUDED.cost, "
                    "  currency   = EXCLUDED.currency, "
                    "  updated_at = now()",
                    rows,
                )
    except Exception:
        logger.warning("Failed to record daily stats to Postgres", exc_info=True)


async def get_telemetry_between(
    start: datetime.datetime, end: datetime.datetime
) -> Optional[list[tuple[datetime.datetime, float]]]:
    """Ordered ``(recorded_at, session_energy_wh)`` rows in ``[start, end]``.

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
                "SELECT recorded_at, session_energy_wh FROM telemetry "
                "WHERE recorded_at >= %s AND recorded_at <= %s "
                "ORDER BY recorded_at",
                (start, end),
            )
            rows = await cur.fetchall()
        return [(row[0], row[1]) for row in rows]
    except Exception:
        logger.warning("Failed to read telemetry from Postgres", exc_info=True)
        return None


async def get_session_telemetry(session_id: int) -> Optional[list[dict[str, Any]]]:
    """Per-poll telemetry for one session's charge curve, oldest first.

    A session spans from its ``plugged_in_at`` up to the *next* session's
    plug-in (or now, for the most recent one). Each point carries the SOC, draw
    and cumulative session energy at that poll, so the dashboard can plot the
    battery climbing through the charge. Returns None when persistence is off,
    the read fails, or the session id is unknown (so the API can 404).
    """
    if _pool is None:
        return None
    try:
        async with _pool.connection() as conn:
            cur = await conn.execute(
                "SELECT plugged_in_at FROM charge_sessions WHERE id = %s", (session_id,)
            )
            row = await cur.fetchone()
            if row is None or row[0] is None:
                return None
            start = row[0]
            # Upper bound is the next plug-in; None means this is the open session.
            cur = await conn.execute(
                "SELECT MIN(plugged_in_at) FROM charge_sessions WHERE plugged_in_at > %s",
                (start,),
            )
            nxt = await cur.fetchone()
            end = nxt[0] if nxt else None

            select = (
                "SELECT recorded_at, battery_percent, power_watts, session_energy_wh "
                "FROM telemetry WHERE recorded_at >= %s "
            )
            if end is not None:
                cur = await conn.execute(
                    select + "AND recorded_at < %s ORDER BY recorded_at", (start, end)
                )
            else:
                cur = await conn.execute(select + "ORDER BY recorded_at", (start,))
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
        (r["start"], r.get("end"), r.get("importKwh"), r.get("carKwh"), r.get("houseKwh"))
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
                    "(interval_start, interval_end, import_kwh, car_kwh, house_kwh) "
                    "VALUES (%s, %s, %s, %s, %s) "
                    "ON CONFLICT (interval_start) DO UPDATE SET "
                    "  interval_end = EXCLUDED.interval_end, "
                    "  import_kwh   = EXCLUDED.import_kwh, "
                    "  car_kwh      = EXCLUDED.car_kwh, "
                    "  house_kwh    = EXCLUDED.house_kwh, "
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
                "SELECT interval_start, interval_end, import_kwh, car_kwh, house_kwh "
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
            }
            for row in rows
        ]
    except Exception:
        logger.warning("Failed to read grid consumption from Postgres", exc_info=True)
        return None
