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
