"""Tests for the optional Postgres persistence layer.

No real database is used. We install a fake connection pool into ``db._pool`` and
assert the SQL/params the helpers emit, plus the contract that every write is a
no-op when disabled and swallows errors when the DB misbehaves.
"""

import datetime as dt
from unittest.mock import patch

import pytest

import db
import config
from state import StatusSnapshot


def test_run_migrations_uses_psycopg_driver(monkeypatch):
    monkeypatch.setattr(config, "DATABASE_URL", "postgresql://user:p%25@db/app")
    with patch("db.command.upgrade") as upgrade:
        db._run_migrations()
    cfg, revision = upgrade.call_args.args
    assert revision == "head"
    assert cfg.get_main_option("sqlalchemy.url") == "postgresql+psycopg://user:p%25@db/app"
    assert cfg.get_main_option("script_location").endswith("/alembic")


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


class _SequenceConn(_FakeConn):
    """Connection returning a different result cursor for each query."""

    def __init__(self, cursors):
        super().__init__(cursors[0])
        self._cursors = iter(cursors)

    async def execute(self, sql, params=None):
        self.executed.append((sql, params))
        return next(self._cursors)


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
    assert params == (
        "IONIQ 5", 62, 80, 18, "configured", 12450, 98,
        None, None, None, None, None, None,
    )


async def test_record_session_uses_idempotency_key_and_identity(fake_pool):
    import datetime as dt

    conn, _ = fake_pool
    observed = dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc)
    assert await db.record_session(
        vehicle_name="IONIQ 5", soc_percent=62, target_percent=80, topup_percent=18,
        action="configured", session_key="session-1", vehicle_id="vehicle-1",
        vin="VIN123", charger_id="charger-1", source_observed_at=observed,
        plugged_in_at=observed,
    ) == 42
    sql, params = conn.executed[0]
    assert "ON CONFLICT (session_key)" in sql
    assert params[7:] == (
        "session-1", "vehicle-1", "VIN123", "charger-1", observed, observed,
    )


async def test_close_session_is_idempotent_update(fake_pool):
    conn, _ = fake_pool
    await db.close_session("session-1", actual_energy_wh=4321.4, end_soc_percent=80)
    sql, params = conn.executed[0]
    assert "UPDATE charge_sessions" in sql
    assert "COALESCE(unplugged_at, now())" in sql
    assert params == (80, 4321, "unplugged", 4321, "session-1")


async def test_complete_session_records_final_measurements(fake_pool):
    conn, _ = fake_pool
    await db.complete_session(
        "session-1", actual_energy_wh=4321.4, end_soc_percent=80
    )
    sql, params = conn.executed[0]
    assert "completed_at = COALESCE(completed_at, now())" in sql
    assert params == (80, 4321, "finished", "session-1")


async def test_record_session_event_wraps_details_as_jsonb(fake_pool):
    conn, _ = fake_pool
    await db.record_session_event(42, "target_configured", {"target": 80})
    sql, params = conn.executed[0]
    assert "INSERT INTO session_events" in sql
    assert params[:2] == (42, "target_configured")
    assert params[2].obj == {"target": 80}


async def test_get_session_id_by_key(fake_pool):
    conn, _ = fake_pool
    assert await db.get_session_id_by_key("session-1") == 42
    assert conn.executed[0][1] == ("session-1",)


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
    completed = dt.datetime(2026, 6, 2, 1, 0, tzinfo=dt.timezone.utc)
    cursor.rows = [
        (3, dt.datetime(2026, 6, 1, 21, 42, tzinfo=dt.timezone.utc), "IONIQ 5", 54, 80, 26, "configured", 12450, 98, 18500, 123, "GBP", "actual_agile", 1.0, "reconciled", completed),
        (2, None, "IONIQ 5", 85, 80, 0, "skipped_at_target", None, None, None, None, None, None, None, "validated", None),
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
            "actualEnergyKwh": 18.5,
            "actualCost": 1.23,
            "costCurrency": "GBP",
            "costMethod": "actual_agile",
            "tariffCoverage": 1.0,
            "quality": "reconciled",
            "completedAt": completed.isoformat(),
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
            "actualEnergyKwh": None,
            "actualCost": None,
            "costCurrency": None,
            "costMethod": None,
            "tariffCoverage": None,
            "quality": "validated",
            "completedAt": None,
        },
    ]


async def test_get_all_sessions_orders_chronologically_unbounded(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    cursor.rows = [
        (1, dt.datetime(2026, 5, 1, 20, 0, tzinfo=dt.timezone.utc), "IONIQ 5", 40, 80, 40, "configured", 12000, 99, None, None, None, None, None, "validated", None),
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


async def test_get_session_audit_maps_all_provenance():
    observed = dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc)
    finished = observed + dt.timedelta(hours=3)
    session = (
        7, "session-7", observed, finished, finished, "IONIQ 5", "car-1", "VIN1",
        "charger-1", observed, 50, 80, 80, 30, "configured", 12000, 98, 18500,
        123, "GBP", "actual_agile", 1.0, 18450, 50, "finished", "reconciled",
        finished,
    )
    conn = _SequenceConn([
        _FakeCursor(row=session),
        _FakeCursor(rows=[(observed, "plugged_in", {"soc_percent": 50})]),
        _FakeCursor(rows=[(observed, observed, observed + dt.timedelta(minutes=30),
                           [{"energy": 3.7}], 1, "initial")]),
        _FakeCursor(rows=[(observed, observed + dt.timedelta(minutes=30), 3700, 25,
                           6.75, "GBP", "measured", "ohme_counter")]),
    ])
    db._pool = _FakePool(conn)
    try:
        audit = await db.get_session_audit(7)
    finally:
        db._pool = None

    assert all(params == (7,) for _, params in conn.executed)
    assert audit["session"]["sessionKey"] == "session-7"
    assert audit["session"]["actualEnergyWh"] == 18500
    assert audit["events"] == [
        {"at": observed, "type": "plugged_in", "details": {"soc_percent": 50}}
    ]
    assert audit["schedules"][0]["revision"] == 1
    assert audit["intervals"][0] == {
        "start": observed,
        "end": observed + dt.timedelta(minutes=30),
        "energyWh": 3700,
        "costMinor": 25,
        "rateMinorPerKwh": 6.75,
        "currency": "GBP",
        "quality": "measured",
        "source": "ohme_counter",
    }


async def test_get_session_audit_none_for_unknown_or_disabled():
    db._pool = _FakePool(_FakeConn(_FakeCursor(row=None)))
    try:
        assert await db.get_session_audit(999) is None
    finally:
        db._pool = None
    assert await db.get_session_audit(1) is None


async def test_get_session_telemetry_maps_points(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    cursor._row = (dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc),)  # session start
    cursor.rows = [
        (dt.datetime(2026, 6, 1, 20, 5, tzinfo=dt.timezone.utc), 62, 7400.0, 1500.0),
        (dt.datetime(2026, 6, 1, 20, 35, tzinfo=dt.timezone.utc), 70, 7300.0, 5200.0),
    ]

    points = await db.get_session_telemetry(7)

    assert "SELECT id FROM charge_sessions WHERE id = %s" in conn.executed[0][0]
    assert conn.executed[0][1] == (7,)
    assert "FROM telemetry WHERE session_id = %s" in conn.executed[1][0]
    assert conn.executed[1][1] == (7,)
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


# --- vehicle-scoped driving metrics -------------------------------------------


async def test_get_single_vehicle_id_requires_exactly_one_distinct_vehicle():
    for row, expected in [(("car-1", 1), "car-1"), (("car-1", 2), None), ((None, 0), None)]:
        conn = _FakeConn(_FakeCursor(row=row))
        db._pool = _FakePool(conn)
        try:
            assert await db.get_single_vehicle_id() == expected
            assert "COUNT(DISTINCT vehicle_id)" in conn.executed[0][0]
        finally:
            db._pool = None


async def test_ingestion_cursor_round_trip_helpers():
    cursor_at = dt.datetime(2026, 7, 9, tzinfo=dt.timezone.utc)
    conn = _FakeConn(_FakeCursor(row=(cursor_at,)))
    db._pool = _FakePool(conn)
    try:
        assert await db.get_ingestion_cursor("octopus_consumption") == cursor_at
        await db.set_ingestion_cursor("octopus_consumption", cursor_at, {"rows": 48})
    finally:
        db._pool = None
    assert "SELECT cursor_at FROM ingestion_cursors" in conn.executed[0][0]
    sql, params = conn.executed[1]
    assert "GREATEST" in sql
    assert params[0:2] == ("octopus_consumption", cursor_at)
    assert params[2].obj == {"rows": 48}


async def test_data_quality_summary_maps_aggregate_counts():
    row = (
        10, 8, 1, 2, 3, 4, dt.date(2026, 7, 8),
        dt.datetime(2026, 7, 9, tzinfo=dt.timezone.utc),
    )
    conn = _FakeConn(_FakeCursor(row=row))
    db._pool = _FakePool(conn)
    try:
        result = await db.get_data_quality_summary()
    finally:
        db._pool = None
    assert result["sessions"] == {
        "total": 10, "completed": 8, "missingActualEnergy": 1, "missingActualCost": 2
    }
    assert result["telemetry"]["unlinkedLast24h"] == 3
    assert result["consumption"]["uncertainLast30d"] == 4


async def test_vehicle_driving_metrics_pairs_only_valid_complete_intervals():
    start = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 6, 8, tzinfo=dt.timezone.utc)
    rows = [
        # Before-window session is fetched for ordering but not attributed.
        (start - dt.timedelta(days=1), 900, 5000, 100, "GBP"),
        (start, 1000, 10000, 250, "GBP"),  # +100 mi, valid energy + cost
        (start + dt.timedelta(days=2), 1100, 8000, None, None),  # regression: ignored
        (start + dt.timedelta(days=3), 1090, 9000, 300, "GBP"),
        (start + dt.timedelta(days=5), 1190, None, 400, "GBP"),  # missing energy: ignored
        (end, 1290, 7000, 500, "GBP"),
    ]
    cursor = _FakeCursor(rows=rows)
    conn = _FakeConn(cursor)
    db._pool = _FakePool(conn)
    try:
        result = await db.get_vehicle_driving_metrics(start, end, "car-1")
    finally:
        db._pool = None

    assert result == {
        "vehicleId": "car-1",
        "milesDriven": 200,
        "energyWh": 19000,
        "intervalCount": 2,
        "from": start,
        "to": start + dt.timedelta(days=5),
        "costMilesDriven": 200,
        "costMinor": 550,
        "costIntervalCount": 2,
        "costCurrency": "GBP",
    }
    sql, params = conn.executed[0]
    assert "WHERE vehicle_id = %s" in sql
    assert params == ("car-1", start, end)


async def test_vehicle_driving_metrics_returns_none_without_vehicle_or_intervals():
    db._pool = _FakePool(_FakeConn(_FakeCursor(rows=[])))
    try:
        start = dt.datetime(2026, 1, 1, tzinfo=dt.timezone.utc)
        assert (
            await db.get_vehicle_driving_metrics(start, start + dt.timedelta(days=1), None)
            is None
        )
        assert (
            await db.get_vehicle_driving_metrics(start, start + dt.timedelta(days=1), "car-1")
            is None
        )
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
    assert params[4:] == (42, "initial")
    assert "MAX(revision)" in sql


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
    await db.record_telemetry(snap, session_id=42)
    sql, params = conn.executed[0]
    assert "INSERT INTO telemetry" in sql
    assert params == (
        "IONIQ 5", 62, "charging", True, True, 7400.0, 32.0, 230, 80, 4500.0,
        42, "session_linked",
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
        {
            "date": "2026-06-01", "energyKwh": 18.5, "savings": 3.7,
            "cost": 2.3, "isComplete": True,
        },
        {"date": None, "energyKwh": 0, "savings": 0, "cost": 0},  # skipped (no date)
        {
            "date": "2026-06-02", "energyKwh": 12.0, "savings": 2.1,
            "cost": 1.4, "isComplete": True,
        },
    ]
    await db.record_daily_stats(daily, "GBP")
    # One executemany with only the two dated rows.
    assert len(cursor.executemany_calls) == 1
    sql, rows = cursor.executemany_calls[0]
    assert "INSERT INTO daily_stats" in sql
    assert "ON CONFLICT (stat_date) DO UPDATE" in sql
    assert rows == [
        ("2026-06-01", 18.5, 3.7, 2.3, "GBP", 18500, 370, 230, True),
        ("2026-06-02", 12.0, 2.1, 1.4, "GBP", 12000, 210, 140, True),
    ]


async def test_record_daily_stats_empty_is_noop(fake_pool):
    _, cursor = fake_pool
    await db.record_daily_stats([], "GBP")
    assert cursor.executemany_calls == []


async def test_record_daily_stats_all_dateless_is_noop(fake_pool):
    _, cursor = fake_pool
    await db.record_daily_stats([{"date": None, "energyKwh": 1}], "GBP")
    assert cursor.executemany_calls == []


async def test_get_monthly_report_rows_maps_exact_units_and_sessions():
    start = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    end = dt.datetime(2026, 7, 1, tzinfo=dt.timezone.utc)
    updated = start + dt.timedelta(days=2)
    conn = _SequenceConn([
        _FakeCursor(rows=[
            (dt.date(2026, 6, 1), 4200, 80, 50, "GBP", "ohme_summary", True, updated),
        ]),
        _FakeCursor(rows=[
            (7, start, updated, 4100, 49, "GBP", "reconciled", "IONIQ 5", "configured"),
        ]),
    ])
    db._pool = _FakePool(conn)
    try:
        report = await db.get_monthly_report_rows(start, end)
    finally:
        db._pool = None

    assert conn.executed[0][1] == (start.date(), end.date())
    assert conn.executed[1][1] == (start, end)
    assert report["daily"][0]["energyWh"] == 4200
    assert report["daily"][0]["isComplete"] is True
    assert report["sessions"][0]["actualCostMinor"] == 49
    assert report["sessions"][0]["action"] == "configured"


async def test_get_monthly_report_rows_none_when_disabled():
    db._pool = None
    now = dt.datetime.now(dt.timezone.utc)
    assert await db.get_monthly_report_rows(now, now) is None


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
    cursor.rows = [
        (t0, 42, 0.0, 7400.0, "charging", True),
        (t0, 42, 1000.0, 7400.0, "charging", True),
    ]
    start = t0
    end = t0 + dt.timedelta(days=1)
    rows = await db.get_telemetry_between(start, end)
    sql, params = conn.executed[0]
    assert "FROM telemetry" in sql and "ORDER BY recorded_at" in sql
    assert params == (start, end)
    assert rows == cursor.rows


async def test_get_session_attribution_rows_filters_by_session(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    t0 = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    cursor.rows = [(t0, 42, 1000.0, 7400.0, "charging", True)]
    assert await db.get_session_attribution_rows(42) == cursor.rows
    assert "WHERE session_id = %s" in conn.executed[0][0]
    assert conn.executed[0][1] == (42,)


async def test_tariff_rate_round_trip_helpers(fake_pool, monkeypatch):
    import datetime as dt
    from decimal import Decimal

    conn, cursor = fake_pool
    monkeypatch.setattr(config, "OCTOPUS_PRODUCT_CODE", "AGILE-TEST")
    monkeypatch.setattr(config, "OCTOPUS_REGION", "A")
    await db.upsert_tariff_rates([{
        "from": "2026-06-01T00:00:00Z",
        "to": "2026-06-01T00:30:00Z",
        "pricePerKwh": 0.1234,
    }])
    _, params = cursor.executemany_calls[0]
    assert params[0][2] == Decimal("12.3400")
    assert params[0][4] == "octopus_agile:AGILE-TEST:A"

    t0 = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    t1 = t0 + dt.timedelta(minutes=30)
    cursor.rows = [(t0, t1, Decimal("12.34"), "GBP", "octopus_agile:AGILE-TEST:A")]
    rates = await db.get_tariff_rates(t0, t1)
    assert rates == [{
        "from": t0.isoformat(), "to": t1.isoformat(), "pricePerKwh": 0.1234,
        "currency": "GBP", "source": "octopus_agile:AGILE-TEST:A",
    }]
    assert conn.executed[-1][1] == (t0, t1)


async def test_record_session_reconciliation_persists_intervals_and_total(fake_pool):
    import datetime as dt
    import octopus

    conn, cursor = fake_pool
    t0 = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    priced = octopus.PricedEnergy(
        intervals=[{
            "start": t0, "end": t0 + dt.timedelta(minutes=30), "energyWh": 1000,
            "costMinor": 10, "rateMinorPerKwh": 10.0, "currency": "GBP",
            "quality": "priced",
        }],
        cost_minor=10,
        coverage=1.0,
        energy_wh=1000,
    )
    await db.record_session_reconciliation(42, priced, counter_energy_wh=1005)
    assert cursor.executemany_calls[0][1][0][0] == 42
    sql, params = conn.executed[-1]
    assert "actual_cost_minor" in sql
    assert params == (10, "GBP", "actual_agile", 1.0, 1000, 5, "reconciled", 42)


async def test_reconciliation_with_energy_mismatch_withholds_actual_cost(fake_pool):
    import octopus

    conn, _ = fake_pool
    priced = octopus.PricedEnergy(cost_minor=10, coverage=1.0, energy_wh=500)
    await db.record_session_reconciliation(42, priced, counter_energy_wh=1000)
    _, params = conn.executed[-1]
    assert params[0:3] == (None, None, None)
    assert params[6] == "energy_mismatch"


async def test_upsert_grid_consumption_inserts_dated_rows(fake_pool):
    _, cursor = fake_pool
    rows = [
        {"start": "2026-06-01T00:00:00+00:00", "end": "2026-06-01T00:30:00+00:00",
         "importKwh": 1.5, "carKwh": 1.0, "houseKwh": 0.5},
        {"start": None, "importKwh": 9},  # skipped (no interval start)
    ]
    assert await db.upsert_grid_consumption(rows) is True
    assert len(cursor.executemany_calls) == 1
    sql, params = cursor.executemany_calls[0]
    assert "INSERT INTO grid_consumption" in sql
    assert "ON CONFLICT (interval_start) DO UPDATE" in sql
    assert params == [
        ("2026-06-01T00:00:00+00:00", "2026-06-01T00:30:00+00:00", 1.5, 1.0, 0.5, 0, "unknown")
    ]


async def test_upsert_grid_consumption_empty_is_noop(fake_pool):
    _, cursor = fake_pool
    assert await db.upsert_grid_consumption([]) is False
    assert cursor.executemany_calls == []


async def test_get_grid_consumption_maps_rows(fake_pool):
    import datetime as dt

    conn, cursor = fake_pool
    t0 = dt.datetime(2026, 6, 1, 0, 0, tzinfo=dt.timezone.utc)
    t1 = t0 + dt.timedelta(minutes=30)
    cursor.rows = [(t0, t1, 1.5, 1.0, 0.5, 0.0, "good")]
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
            "unattributedKwh": 0.0,
            "quality": "good",
        }
    ]
