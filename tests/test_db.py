"""Tests for the optional Postgres persistence layer.

No real database is used. We install a fake connection pool into ``db._pool`` and
assert the SQL/params the helpers emit, plus the contract that every write is a
no-op when disabled and swallows errors when the DB misbehaves.
"""

import pytest

import db
from state import StatusSnapshot


class _FakeCursor:
    def __init__(self, row=None, rows=None):
        self._row = row
        self.rows = rows or []
        self.executed: list[tuple] = []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    async def fetchone(self):
        return self._row

    async def fetchall(self):
        return self.rows

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeConn:
    def __init__(self, cursor):
        self._cursor = cursor
        self.executed: list[tuple] = []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self._cursor

    def cursor(self):
        return self._cursor


class _FakeConnCtx:
    def __init__(self, conn):
        self._conn = conn

    async def __aenter__(self):
        return self._conn

    async def __aexit__(self, *exc):
        return False


class _FakePool:
    def __init__(self, conn):
        self._conn = conn

    def connection(self):
        return _FakeConnCtx(self._conn)


class _BoomPool:
    def connection(self):
        raise RuntimeError("db is down")


@pytest.fixture
def fake_pool():
    """Install a fake pool into db and tear it down afterwards."""
    cursor = _FakeCursor(row=(42,))
    conn = _FakeConn(cursor)
    db._pool = _FakePool(conn)
    yield conn, cursor
    db._pool = None


# --- disabled = no-op ----------------------------------------------------------


async def test_writes_are_noops_when_disabled():
    db._pool = None
    assert await db.record_session(
        vehicle_name="EV", soc_percent=50, target_percent=80, topup_percent=30, action="configured"
    ) is None
    # None of these should raise.
    await db.record_schedule(session_id=None, slots=[], next_slot_start=None, next_slot_end=None)
    await db.record_telemetry(StatusSnapshot())
    await db.record_daily_stats([{"date": "2026-06-01", "energyKwh": 1}], "GBP")


# --- charge session ------------------------------------------------------------


async def test_record_session_inserts_and_returns_id(fake_pool):
    conn, _ = fake_pool
    session_id = await db.record_session(
        vehicle_name="IONIQ 5", soc_percent=62, target_percent=80, topup_percent=18,
        action="configured", odometer_miles=12450,
    )
    assert session_id == 42
    sql, params = conn.executed[0]
    assert "INSERT INTO charge_sessions" in sql
    assert "RETURNING id" in sql
    assert params == ("IONIQ 5", 62, 80, 18, "configured", 12450)


async def test_record_session_swallows_errors():
    db._pool = _BoomPool()
    try:
        result = await db.record_session(
            vehicle_name="EV", soc_percent=1, target_percent=2, topup_percent=1, action="configured"
        )
    finally:
        db._pool = None
    assert result is None  # error swallowed, no exception


# --- session history -------------------------------------------------------------


async def test_get_recent_sessions_maps_rows(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    cursor.rows = [
        (3, dt.datetime(2026, 6, 1, 21, 42, tzinfo=dt.timezone.utc), "IONIQ 5", 54, 80, 26, "configured", 12450),
        (2, None, "IONIQ 5", 85, 80, 0, "skipped_at_target", None),
    ]

    sessions = await db.get_recent_sessions(10)

    sql, params = conn.executed[0]
    assert "ORDER BY plugged_in_at DESC" in sql
    assert params == (10,)
    assert sessions == [
        {
            "id": 3,
            "pluggedInAt": "2026-06-01T21:42:00+00:00",
            "vehicleName": "IONIQ 5",
            "socPercent": 54,
            "targetPercent": 80,
            "topupPercent": 26,
            "action": "configured",
            "odometerMiles": 12450,
        },
        {
            "id": 2,
            "pluggedInAt": None,
            "vehicleName": "IONIQ 5",
            "socPercent": 85,
            "targetPercent": 80,
            "topupPercent": 0,
            "action": "skipped_at_target",
            "odometerMiles": None,
        },
    ]


async def test_get_recent_sessions_none_when_disabled():
    db._pool = None
    assert await db.get_recent_sessions(10) is None


async def test_get_recent_sessions_none_on_error():
    db._pool = _BoomPool()
    try:
        assert await db.get_recent_sessions(10) is None
    finally:
        db._pool = None


# --- schedule ------------------------------------------------------------------


async def test_record_schedule_wraps_slots_as_jsonb(fake_pool):
    conn, _ = fake_pool
    slots = [{"start": "01:00", "end": "03:30", "power": 7.4}]
    await db.record_schedule(session_id=42, slots=slots, next_slot_start=None, next_slot_end=None)
    sql, params = conn.executed[0]
    assert "INSERT INTO schedule_snapshots" in sql
    assert params[0] == 42
    # The slots are passed through psycopg's Jsonb adapter (carries the original obj).
    assert params[3].obj == slots


# --- telemetry -----------------------------------------------------------------


async def test_record_telemetry_maps_snapshot_fields(fake_pool):
    conn, _ = fake_pool
    snap = StatusSnapshot(
        vehicle_name="IONIQ 5",
        battery_percent=62,
        charger_status="charging",
        connected=True,
        charger_online=True,
        power_watts=7400.0,
        power_amps=32.0,
        power_volts=230,
        target_percent=80,
        session_energy_wh=4500.0,
    )
    await db.record_telemetry(snap)
    sql, params = conn.executed[0]
    assert "INSERT INTO telemetry" in sql
    assert params == (
        "IONIQ 5", 62, "charging", True, True, 7400.0, 32.0, 230, 80, 4500.0,
    )


# --- telemetry retention ---------------------------------------------------------


async def test_prune_telemetry_deletes_rows_older_than_retention(fake_pool):
    conn, _ = fake_pool
    await db.prune_telemetry(365)
    sql, params = conn.executed[0]
    assert "DELETE FROM telemetry" in sql
    assert params == (365,)


async def test_prune_telemetry_zero_retention_keeps_everything(fake_pool):
    conn, _ = fake_pool
    await db.prune_telemetry(0)
    assert conn.executed == []


async def test_prune_telemetry_noop_when_disabled():
    db._pool = None
    await db.prune_telemetry(365)  # must not raise


async def test_prune_telemetry_swallows_errors():
    db._pool = _BoomPool()
    try:
        await db.prune_telemetry(365)  # must not raise
    finally:
        db._pool = None


# --- daily stats ---------------------------------------------------------------


async def test_record_daily_stats_upserts_each_dated_row(fake_pool):
    _, cursor = fake_pool
    daily = [
        {"date": "2026-06-01", "energyKwh": 18.5, "savings": 3.7, "cost": 2.3},
        {"date": None, "energyKwh": 0, "savings": 0, "cost": 0},  # skipped (no date)
        {"date": "2026-06-02", "energyKwh": 12.0, "savings": 2.1, "cost": 1.4},
    ]
    await db.record_daily_stats(daily, "GBP")
    # Only the two dated rows are written.
    assert len(cursor.executed) == 2
    sql, params = cursor.executed[0]
    assert "INSERT INTO daily_stats" in sql
    assert "ON CONFLICT (stat_date) DO UPDATE" in sql
    assert params == ("2026-06-01", 18.5, 3.7, 2.3, "GBP")


async def test_record_daily_stats_empty_is_noop(fake_pool):
    _, cursor = fake_pool
    await db.record_daily_stats([], "GBP")
    assert cursor.executed == []
