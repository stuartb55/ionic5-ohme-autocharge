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
        self.executemany_calls: list[tuple] = []

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return self

    async def executemany(self, sql, params_seq):
        self.executemany_calls.append((sql, list(params_seq)))
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
        action="configured", odometer_miles=12450, soh_percent=98,
    )
    assert session_id == 42
    sql, params = conn.executed[0]
    assert "INSERT INTO charge_sessions" in sql
    assert "RETURNING id" in sql
    assert params == ("IONIQ 5", 62, 80, 18, "configured", 12450, 98)


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
        (3, dt.datetime(2026, 6, 1, 21, 42, tzinfo=dt.timezone.utc), "IONIQ 5", 54, 80, 26, "configured", 12450, 98),
        (2, None, "IONIQ 5", 85, 80, 0, "skipped_at_target", None, None),
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
            "sohPercent": 98,
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
            "sohPercent": None,
        },
    ]


async def test_get_all_sessions_orders_chronologically_unbounded(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    cursor.rows = [
        (1, dt.datetime(2026, 5, 1, 20, 0, tzinfo=dt.timezone.utc), "IONIQ 5", 40, 80, 40, "configured", 12000, 99),
    ]

    sessions = await db.get_all_sessions()

    sql, params = conn.executed[0]
    assert "ORDER BY plugged_in_at ASC" in sql
    assert "LIMIT" not in sql
    assert params is None  # no parameters — full unbounded read
    assert sessions[0]["id"] == 1
    assert sessions[0]["pluggedInAt"] == "2026-05-01T20:00:00+00:00"


async def test_get_all_sessions_none_when_disabled():
    db._pool = None
    assert await db.get_all_sessions() is None


async def test_get_session_telemetry_maps_points(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    cursor._row = (dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc),)  # session start
    cursor.rows = [
        (dt.datetime(2026, 6, 1, 20, 5, tzinfo=dt.timezone.utc), 62, 7400.0, 1500.0),
        (dt.datetime(2026, 6, 1, 20, 35, tzinfo=dt.timezone.utc), 70, 7300.0, 5200.0),
    ]

    points = await db.get_session_telemetry(7)

    assert "FROM charge_sessions WHERE id = %s" in conn.executed[0][0]
    assert conn.executed[0][1] == (7,)
    assert points == [
        {"at": "2026-06-01T20:05:00+00:00", "socPercent": 62,
         "powerWatts": 7400.0, "sessionEnergyKwh": 1.5},
        {"at": "2026-06-01T20:35:00+00:00", "socPercent": 70,
         "powerWatts": 7300.0, "sessionEnergyKwh": 5.2},
    ]


async def test_get_session_telemetry_none_for_unknown_session(fake_pool):
    _, cursor = fake_pool
    cursor._row = None  # session id not found
    assert await db.get_session_telemetry(999) is None


async def test_get_session_telemetry_none_when_disabled():
    db._pool = None
    assert await db.get_session_telemetry(1) is None


async def test_get_soh_history_collapses_unchanged_readings(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    # Rows come newest-first from SQL; oldest-first the SoH goes 100, 100, 99, 99, 97.
    # Consecutive duplicates collapse to one point per change.
    cursor.rows = [
        (dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc), 97),
        (dt.datetime(2026, 5, 1, tzinfo=dt.timezone.utc), 99),
        (dt.datetime(2026, 4, 1, tzinfo=dt.timezone.utc), 99),
        (dt.datetime(2026, 2, 1, tzinfo=dt.timezone.utc), 100),
        (dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc), 100),
    ]

    history = await db.get_soh_history(90)

    sql, params = conn.executed[0]
    assert "soh_percent IS NOT NULL" in sql
    assert params == (90,)
    assert history == [
        {"date": "2026-01-01T00:00:00+00:00", "sohPercent": 100},
        {"date": "2026-04-01T00:00:00+00:00", "sohPercent": 99},
        {"date": "2026-06-01T00:00:00+00:00", "sohPercent": 97},
    ]


async def test_get_soh_history_none_when_disabled():
    db._pool = None
    assert await db.get_soh_history(90) is None


async def test_get_soh_history_none_on_error():
    db._pool = _BoomPool()
    try:
        assert await db.get_soh_history(90) is None
    finally:
        db._pool = None


async def test_get_recent_sessions_none_when_disabled():
    db._pool = None
    assert await db.get_recent_sessions(10) is None


async def test_get_recent_sessions_none_on_error():
    db._pool = _BoomPool()
    try:
        assert await db.get_recent_sessions(10) is None
    finally:
        db._pool = None


# --- odometer / efficiency ------------------------------------------------------


async def test_get_miles_driven_returns_span(fake_pool):
    import datetime as dt

    conn, _ = fake_pool  # default fake cursor returns row (42,)
    miles = await db.get_miles_driven(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc))
    assert miles == 42
    sql, _params = conn.executed[0]
    assert "MAX(odometer_miles) - MIN(odometer_miles)" in sql
    assert "HAVING COUNT(odometer_miles) >= 2" in sql  # never report from a lone reading


async def test_get_miles_driven_none_when_insufficient_data():
    import datetime as dt

    # fetchone returns None when the HAVING clause filters out the single group.
    db._pool = _FakePool(_FakeConn(_FakeCursor(row=None)))
    try:
        assert await db.get_miles_driven(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)) is None
    finally:
        db._pool = None


async def test_get_miles_driven_none_when_disabled():
    import datetime as dt

    db._pool = None
    assert await db.get_miles_driven(dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)) is None


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
    # One executemany with only the two dated rows.
    assert len(cursor.executemany_calls) == 1
    sql, rows = cursor.executemany_calls[0]
    assert "INSERT INTO daily_stats" in sql
    assert "ON CONFLICT (stat_date) DO UPDATE" in sql
    assert rows == [
        ("2026-06-01", 18.5, 3.7, 2.3, "GBP"),
        ("2026-06-02", 12.0, 2.1, 1.4, "GBP"),
    ]


async def test_record_daily_stats_empty_is_noop(fake_pool):
    _, cursor = fake_pool
    await db.record_daily_stats([], "GBP")
    assert cursor.executemany_calls == []


async def test_record_daily_stats_all_dateless_is_noop(fake_pool):
    _, cursor = fake_pool
    await db.record_daily_stats([{"date": None, "energyKwh": 1}], "GBP")
    assert cursor.executemany_calls == []


# --- grid consumption ------------------------------------------------------------


async def test_grid_consumption_helpers_are_noops_when_disabled():
    import datetime as dt

    db._pool = None
    now = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    assert await db.get_telemetry_between(now, now) is None
    assert await db.get_grid_consumption(now, now) is None
    await db.upsert_grid_consumption([{"start": now.isoformat(), "importKwh": 1}])  # no raise


async def test_get_telemetry_between_maps_rows(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    t0 = dt.datetime(2026, 6, 1, 0, 0, tzinfo=dt.timezone.utc)
    cursor.rows = [(t0, 0.0), (t0, 1000.0)]
    start = t0
    end = t0 + dt.timedelta(days=1)
    rows = await db.get_telemetry_between(start, end)
    sql, params = conn.executed[0]
    assert "FROM telemetry" in sql and "ORDER BY recorded_at" in sql
    assert params == (start, end)
    assert rows == [(t0, 0.0), (t0, 1000.0)]


async def test_upsert_grid_consumption_inserts_dated_rows(fake_pool):
    _, cursor = fake_pool
    rows = [
        {"start": "2026-06-01T00:00:00+00:00", "end": "2026-06-01T00:30:00+00:00",
         "importKwh": 1.5, "carKwh": 1.0, "houseKwh": 0.5},
        {"start": None, "importKwh": 9},  # skipped (no interval start)
    ]
    await db.upsert_grid_consumption(rows)
    assert len(cursor.executemany_calls) == 1
    sql, params = cursor.executemany_calls[0]
    assert "INSERT INTO grid_consumption" in sql
    assert "ON CONFLICT (interval_start) DO UPDATE" in sql
    assert params == [("2026-06-01T00:00:00+00:00", "2026-06-01T00:30:00+00:00", 1.5, 1.0, 0.5)]


async def test_upsert_grid_consumption_empty_is_noop(fake_pool):
    _, cursor = fake_pool
    await db.upsert_grid_consumption([])
    assert cursor.executemany_calls == []


async def test_get_grid_consumption_maps_rows(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    t0 = dt.datetime(2026, 6, 1, 0, 0, tzinfo=dt.timezone.utc)
    t1 = t0 + dt.timedelta(minutes=30)
    cursor.rows = [(t0, t1, 1.5, 1.0, 0.5)]
    start = t0
    end = t0 + dt.timedelta(days=1)
    out = await db.get_grid_consumption(start, end)
    sql, params = conn.executed[0]
    assert "FROM grid_consumption" in sql and "ORDER BY interval_start" in sql
    assert params == (start, end)
    assert out == [
        {
            "start": "2026-06-01T00:00:00+00:00",
            "end": "2026-06-01T00:30:00+00:00",
            "importKwh": 1.5,
            "carKwh": 1.0,
            "houseKwh": 0.5,
        }
    ]
