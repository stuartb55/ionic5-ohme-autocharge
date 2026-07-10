"""Tests for the FastAPI backend.

Polling is disabled (see conftest) so the app starts without touching Ohme. We
drive the read endpoints by injecting a snapshot into ``state.store`` and the
statistics endpoint by mocking the client's ``async_get_charge_summary``.
"""

import logging
import os
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi.testclient import TestClient

import api
import bluelink
import config
import settings
from state import StatusSnapshot, store


def _vstate(soc, *, range_miles=150, odometer_miles=10000):
    """Build a Bluelink VehicleState for patching bluelink.get_vehicle_state."""
    return bluelink.VehicleState(soc=soc, range_miles=range_miles, odometer_miles=odometer_miles)


@pytest.fixture
def client():
    # The SPA sends X-Requested-With on every request; mirror that here so the
    # CSRF guard on the simple-request POST endpoints is satisfied by default.
    # Tests that assert the guard fires send their own request without it.
    with TestClient(api.app, headers={"X-Requested-With": "test"}) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_state():
    store.status = StatusSnapshot()
    store.client = None
    store.ready = False
    store.last_soc = None
    store.last_range_miles = None
    store.last_odometer_miles = None
    store.last_soh_percent = None
    store.last_is_locked = None
    store.last_latitude = None
    store.last_longitude = None
    store.last_soc_at = None
    store.charge_target_override = None
    store.ready_by = None
    store.day_targets = {}
    store.vehicle_id_override = None
    store.avg_price_per_kwh = None
    store.price_currency = None
    store.agile_rates = None
    store.last_poll_error = None
    store.consecutive_poll_failures = 0
    store.plugin_failure_notified = False
    store.active_session_id = None
    store.active_session_key = None
    store.last_digest_date = None
    api._last_telemetry_sig = None
    api._summary_cache.update(key=None, value=None, at=0.0)
    api._tariff_cache.update(value=None, at=0.0)
    api._last_refresh_at = None
    if os.path.exists(settings.SETTINGS_PATH):
        os.remove(settings.SETTINGS_PATH)
    yield


def _populate_snapshot():
    store.update(
        StatusSnapshot(
            vehicle_name="Hyundai IONIQ 5",
            battery_percent=62,
            charger_status="charging",
            connected=True,
            charger_online=True,
            charger_model="Home Pro",
            power_watts=7400.0,
            power_amps=32.0,
            power_volts=230,
            target_percent=80,
            session_energy_wh=4500.0,
            slots=[
                {"start": "2026-06-02T01:00:00+01:00", "end": "2026-06-02T03:30:00+01:00",
                 "power": 7.4, "energy": 18.5}
            ],
            next_slot_start="2026-06-02T01:00:00+01:00",
            next_slot_end="2026-06-02T03:30:00+01:00",
            projected_finish="2026-06-02T03:30:00+01:00",
            updated_at="2026-06-02T00:00:00+01:00",
        )
    )


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


def test_version_reports_app_version(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "abc1234")
    assert client.get("/api/version").json() == {"version": "abc1234"}


def test_version_defaults_to_dev(client, monkeypatch):
    monkeypatch.setattr(config, "APP_VERSION", "")
    assert client.get("/api/version").json() == {"version": "dev"}


def test_health_503_when_poll_task_dead(client):
    dead = MagicMock()
    dead.done.return_value = True
    with patch.object(api, "DISABLE_POLLING", False), patch.object(api, "_poll_task", dead):
        resp = client.get("/api/health")
    assert resp.status_code == 503
    body = resp.json()
    assert body["status"] == "error"
    assert body["pollAlive"] is False


def test_health_ok_while_poll_task_running(client):
    alive = MagicMock()
    alive.done.return_value = False
    with patch.object(api, "DISABLE_POLLING", False), patch.object(api, "_poll_task", alive):
        resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["pollAlive"] is True


def test_health_reports_last_error(client):
    _populate_snapshot()
    store.record_poll_failure("poll_failed")
    body = client.get("/api/health").json()
    assert body["lastError"] == "poll_failed"
    assert body["lastSuccessfulPoll"] == "2026-06-02T00:00:00+01:00"


def test_status_reflects_snapshot(client):
    _populate_snapshot()
    body = client.get("/api/status").json()

    assert body["vehicle"]["name"] == "Hyundai IONIQ 5"
    assert body["vehicle"]["batteryPercent"] == 62
    assert body["charger"]["status"] == "charging"
    assert body["charger"]["connected"] is True
    assert body["charger"]["power"]["watts"] == 7400.0
    assert body["charger"]["targetPercent"] == 80
    assert body["charger"]["sessionEnergyKwh"] == 4.5  # 4500 Wh -> kWh
    assert body["charger"]["projectedFinish"] == "2026-06-02T03:30:00+01:00"
    assert body["config"]["chargeTarget"] == 80
    assert body["ready"] is True


def test_status_serialises_vehicle_health(client):
    store.update(
        StatusSnapshot(
            connected=True,
            aux_battery_percent=85,
            tyre_pressure_warning=True,
            washer_fluid_warning=False,
            key_battery_warning=None,
            open_items=["Boot"],
        )
    )
    health = client.get("/api/status").json()["vehicle"]["health"]
    assert health == {
        "auxBatteryPercent": 85,
        "tyrePressureWarning": True,
        "washerFluidWarning": False,
        "keyBatteryWarning": None,
        "openItems": ["Boot"],
    }


def test_status_before_first_poll_is_empty_but_ok(client):
    body = client.get("/api/status").json()
    assert body["ready"] is False
    assert body["vehicle"]["batteryPercent"] is None
    assert body["charger"]["connected"] is False


def test_poll_failure_preserves_snapshot_and_reports_error(client):
    _populate_snapshot()
    store.record_poll_failure("poll_failed")

    body = client.get("/api/status").json()

    # Last good data is still served…
    assert body["vehicle"]["batteryPercent"] == 62
    assert body["charger"]["status"] == "charging"
    # …and the failure is reported alongside it.
    assert body["lastError"] == "poll_failed"


def test_successful_poll_clears_last_error(client):
    store.record_poll_failure("poll_failed")
    _populate_snapshot()
    body = client.get("/api/status").json()
    assert body["lastError"] is None


async def test_make_client_with_retry_eventually_succeeds():
    ohme = MagicMock()
    with (
        patch(
            "ohme_client.make_client",
            new=AsyncMock(side_effect=[RuntimeError("boom"), RuntimeError("boom"), ohme]),
        ),
        patch("asyncio.sleep", new=AsyncMock()) as mock_sleep,
    ):
        result = await api._make_client_with_retry()

    assert result is ohme
    # Two failures -> two backoff sleeps (5s then 10s), then success.
    assert [c.args[0] for c in mock_sleep.await_args_list] == [5.0, 10.0]
    # The failures were recorded so /api/health can report them while retrying.
    assert store.last_poll_error == "login_failed"


def test_schedule_returns_slots(client):
    _populate_snapshot()
    body = client.get("/api/schedule").json()
    assert len(body["slots"]) == 1
    assert body["slots"][0]["power"] == 7.4
    assert body["nextSlotStart"] == "2026-06-02T01:00:00+01:00"
    assert body["connected"] is True


def test_security_headers_present(client):
    resp = client.get("/api/health")
    assert resp.headers["x-content-type-options"] == "nosniff"
    assert resp.headers["x-frame-options"] == "DENY"


def test_statistics_503_when_no_client(client):
    resp = client.get("/api/statistics")
    assert resp.status_code == 503


def test_statistics_parses_summary(client):
    # Ohme returns Money amounts in minor units (pence for GBP); the backend
    # converts to pounds.
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(
        return_value={
            "granularity": "DAY",
            "totalStats": {
                "energyChargedTotalWh": 42000,
                "costStats": {
                    "moneyCostTotal": {"currencyCode": "GBP", "amount": "525"},
                    "moneySavedVsStandardTariff": {"currencyCode": "GBP", "amount": "840"},
                    "averageKwhPrice": {"currencyCode": "GBP", "amount": "7.284"},
                },
                "carbonStats": {"carbonSavedVsGasCarGrams": 12000},
            },
            "stats": [
                {
                    "startTime": 1748822400000,
                    "energyChargedTotalWh": 18500,
                    "costStats": {
                        "moneyCostTotal": {"currencyCode": "GBP", "amount": "230"},
                        "moneySavedVsStandardTariff": {"currencyCode": "GBP", "amount": "370"},
                    },
                }
            ],
        }
    )
    store.client = mock_client

    body = client.get("/api/statistics?days=7").json()

    assert body["rangeDays"] == 7
    assert body["currency"] == "GBP"
    assert body["totals"]["energyKwh"] == 42.0
    assert body["totals"]["costTotal"] == 5.25  # 525p -> £5.25
    assert body["totals"]["savingsVsStandard"] == 8.4  # 840p -> £8.40
    # 7.284p/kWh -> £0.07284, rounded to 4dp. The frontend renders this as "7.3p".
    assert body["totals"]["averageKwhPrice"] == 0.0728
    assert body["totals"]["carbonSavedKgVsGasCar"] == 12.0
    assert len(body["daily"]) == 1
    assert body["daily"][0]["energyKwh"] == 18.5
    assert body["daily"][0]["cost"] == 2.3  # 230p -> £2.30
    assert body["daily"][0]["savings"] == 3.7  # 370p -> £3.70


def _summary_client(energy_wh=42000):
    """An Ohme client whose summary reports a fixed total energy, no daily rows."""
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(
        return_value={"granularity": "DAY", "totalStats": {"energyChargedTotalWh": energy_wh}, "stats": []}
    )
    return mock_client


def test_statistics_includes_efficiency_when_data_available(client):
    store.client = _summary_client(energy_wh=42000)  # 42 kWh charged
    with patch("db.is_enabled", return_value=True), \
         patch("db.get_miles_driven", new=AsyncMock(return_value=168)) as mock_miles:
        body = client.get("/api/statistics?days=30").json()

    # 168 miles driven / 42 kWh charged = 4.0 mi/kWh
    assert body["efficiency"] == {"milesDriven": 168, "milesPerKwh": 4.0}
    mock_miles.assert_awaited_once()


def test_statistics_efficiency_null_when_persistence_disabled(client):
    store.client = _summary_client()
    with patch("db.is_enabled", return_value=False):
        body = client.get("/api/statistics?days=7").json()
    assert body["efficiency"] is None


def test_statistics_includes_period_comparison(client):
    cur = {
        "granularity": "DAY",
        "totalStats": {
            "energyChargedTotalWh": 42000,
            "costStats": {"moneyCostTotal": {"amount": "525", "currencyCode": "GBP"}},
        },
        "stats": [],
    }
    prev = {
        "granularity": "DAY",
        "totalStats": {
            "energyChargedTotalWh": 30000,
            "costStats": {"moneyCostTotal": {"amount": "400", "currencyCode": "GBP"}},
        },
        "stats": [],
    }
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(side_effect=[cur, prev])
    store.client = mock_client

    body = client.get("/api/statistics?days=7").json()
    assert body["comparison"]["previous"]["energyKwh"] == 30.0
    assert body["comparison"]["previous"]["costTotal"] == 4.0  # 400p -> £4


def test_statistics_comparison_null_when_previous_fetch_fails(client):
    cur = {"granularity": "DAY", "totalStats": {"energyChargedTotalWh": 42000}, "stats": []}
    mock_client = MagicMock()
    # Current fetch succeeds; the previous-window fetch raises.
    mock_client.async_get_charge_summary = AsyncMock(side_effect=[cur, RuntimeError("boom")])
    store.client = mock_client

    body = client.get("/api/statistics?days=7").json()
    assert body["comparison"] is None


def test_statistics_efficiency_null_when_no_odometer_span(client):
    store.client = _summary_client()
    with patch("db.is_enabled", return_value=True), \
         patch("db.get_miles_driven", new=AsyncMock(return_value=None)):
        body = client.get("/api/statistics?days=90").json()
    assert body["efficiency"] is None


def _summary_client_with_cost(energy_wh=42000, cost_minor="5250"):
    """An Ohme client whose summary reports total energy and a total cost."""
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(
        return_value={
            "granularity": "DAY",
            "totalStats": {
                "energyChargedTotalWh": energy_wh,
                "costStats": {"moneyCostTotal": {"amount": cost_minor, "currencyCode": "GBP"}},
            },
            "stats": [],
        }
    )
    return mock_client


def test_statistics_includes_running_cost_when_data_available(client):
    store.client = _summary_client_with_cost(cost_minor="5250")  # £52.50 spent
    with patch("db.is_enabled", return_value=True), \
         patch("db.get_miles_driven", new=AsyncMock(return_value=210)):
        body = client.get("/api/statistics?days=30").json()
    # £52.50 / 210 miles = £0.25 per mile
    assert body["runningCost"] == {"costPerMile": 0.25, "milesDriven": 210, "costTotal": 52.5}


def test_statistics_running_cost_null_without_miles(client):
    store.client = _summary_client_with_cost()
    with patch("db.is_enabled", return_value=True), \
         patch("db.get_miles_driven", new=AsyncMock(return_value=None)):
        body = client.get("/api/statistics?days=30").json()
    assert body["runningCost"] is None


def test_statistics_running_cost_null_without_cost(client):
    store.client = _summary_client()  # no costStats -> costTotal 0
    with patch("db.is_enabled", return_value=True), \
         patch("db.get_miles_driven", new=AsyncMock(return_value=210)):
        body = client.get("/api/statistics?days=30").json()
    assert body["runningCost"] is None


def test_parse_summary_buckets_days_in_account_timezone():
    import datetime as dt
    from zoneinfo import ZoneInfo

    # 23:30 UTC on June 1st is 00:30 BST on June 2nd — Ohme's day bucket belongs
    # to June 2nd even when the host (CI, container default) runs UTC. Pin the
    # configured zone so the assertion doesn't depend on the host's TZ env.
    start = dt.datetime(2025, 6, 1, 23, 30, tzinfo=dt.timezone.utc)
    summary = {
        "totalStats": {},
        "stats": [{"startTime": int(start.timestamp() * 1000), "energyChargedTotalWh": 1000}],
    }

    with patch.object(api, "_STATS_TZ", ZoneInfo("Europe/London")):
        parsed = api.parse_summary(summary, 7)

    assert parsed["daily"][0]["date"] == "2025-06-02"


def test_statistics_validates_days_range(client):
    store.client = MagicMock()
    assert client.get("/api/statistics?days=0").status_code == 422
    assert client.get("/api/statistics?days=1000").status_code == 422


def test_statistics_502_on_upstream_error(client):
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(side_effect=RuntimeError("boom"))
    store.client = mock_client
    assert client.get("/api/statistics").status_code == 502


# --- force refresh -------------------------------------------------------------


def test_refresh_503_when_no_client(client):
    resp = client.post("/api/refresh")
    assert resp.status_code == 503


def test_refresh_rebuilds_snapshot_and_clears_stats_cache(client):
    mock_client = _charging_client()
    mock_client.async_get_charge_session = AsyncMock()
    store.client = mock_client
    # Seed a stale stats cache to prove refresh invalidates it.
    api._summary_cache.update(key="days=7", value={"stale": True}, at=9e9)

    resp = client.post("/api/refresh")

    assert resp.status_code == 200
    body = resp.json()
    assert body["ok"] is True
    assert body["ready"] is True
    mock_client.async_get_charge_session.assert_awaited()
    # Snapshot was rebuilt from the live client (CHARGING status => connected).
    assert store.status.connected is True
    assert store.status.charger_status == "charging"
    # Stats cache was dropped.
    assert api._summary_cache["value"] is None


def test_refresh_rate_limited_within_min_interval(client):
    mock_client = _charging_client()
    mock_client.async_get_charge_session = AsyncMock()
    mock_client._charge_session = {"mode": "SMART_CHARGE"}
    store.client = mock_client

    assert client.post("/api/refresh").status_code == 200
    resp = client.post("/api/refresh")

    assert resp.status_code == 429
    assert int(resp.headers["Retry-After"]) >= 1
    # Only the first call reached Ohme.
    assert mock_client.async_get_charge_session.await_count == 1


def test_refresh_502_on_upstream_error(client):
    mock_client = MagicMock()
    mock_client.async_get_charge_session = AsyncMock(side_effect=RuntimeError("boom"))
    store.client = mock_client
    assert client.post("/api/refresh").status_code == 502


# --- session history --------------------------------------------------------------


def test_sessions_disabled_when_persistence_off(client):
    with patch("db.get_recent_sessions", new=AsyncMock(return_value=None)):
        body = client.get("/api/sessions").json()
    assert body == {"enabled": False, "sessions": []}


def test_sessions_returns_rows_and_passes_limit(client):
    rows = [{"id": 1, "pluggedInAt": "2026-06-01T21:42:00+00:00", "action": "configured"}]
    with patch("db.get_recent_sessions", new=AsyncMock(return_value=rows)) as mock_get:
        body = client.get("/api/sessions?limit=5").json()

    assert body["enabled"] is True
    assert body["sessions"] == rows
    mock_get.assert_awaited_once_with(5)


def test_sessions_validates_limit(client):
    assert client.get("/api/sessions?limit=0").status_code == 422
    assert client.get("/api/sessions?limit=100").status_code == 422


def test_sessions_export_404_when_persistence_off(client):
    with patch("db.get_all_sessions", new=AsyncMock(return_value=None)):
        res = client.get("/api/sessions/export")
    assert res.status_code == 404


def test_sessions_export_csv(client):
    rows = [
        {
            "id": 1,
            "pluggedInAt": "2026-06-01T21:42:00+00:00",
            "vehicleName": "IONIQ 5",
            "socPercent": 62,
            "targetPercent": 80,
            "topupPercent": 18,
            "action": "configured",
            "odometerMiles": 12000,
            "sohPercent": 99,
        }
    ]
    with patch("db.get_all_sessions", new=AsyncMock(return_value=rows)) as mock_get:
        res = client.get("/api/sessions/export?format=csv")

    mock_get.assert_awaited_once_with()
    assert res.status_code == 200
    assert res.headers["content-type"].startswith("text/csv")
    assert "attachment; filename=" in res.headers["content-disposition"]
    lines = res.text.strip().splitlines()
    assert lines[0].split(",") == [
        "id", "pluggedInAt", "vehicleName", "socPercent", "targetPercent",
        "topupPercent", "action", "odometerMiles", "sohPercent", "actualEnergyKwh",
        "actualCost", "costCurrency", "costMethod", "tariffCoverage", "quality", "completedAt",
    ]
    assert lines[1].startswith("1,2026-06-01T21:42:00+00:00,IONIQ 5,62,80,18,configured")


def test_sessions_export_json(client):
    rows = [{"id": 1, "pluggedInAt": "2026-06-01T21:42:00+00:00", "action": "configured"}]
    with patch("db.get_all_sessions", new=AsyncMock(return_value=rows)):
        res = client.get("/api/sessions/export?format=json")

    assert res.status_code == 200
    assert res.headers["content-type"].startswith("application/json")
    assert "attachment; filename=" in res.headers["content-disposition"]
    assert res.json() == rows


def test_sessions_export_rejects_bad_format(client):
    assert client.get("/api/sessions/export?format=xml").status_code == 422


def test_session_telemetry_disabled_when_persistence_off(client):
    with patch("db.is_enabled", return_value=False):
        body = client.get("/api/sessions/1/telemetry").json()
    assert body == {"enabled": False, "points": []}


def test_session_telemetry_404_for_unknown_session(client):
    with (
        patch("db.is_enabled", return_value=True),
        patch("db.get_session_telemetry", new=AsyncMock(return_value=None)),
    ):
        res = client.get("/api/sessions/999/telemetry")
    assert res.status_code == 404


def test_session_telemetry_returns_points(client):
    pts = [{"at": "2026-06-01T20:05:00+00:00", "socPercent": 62,
            "powerWatts": 7400.0, "sessionEnergyKwh": 1.5}]
    with (
        patch("db.is_enabled", return_value=True),
        patch("db.get_session_telemetry", new=AsyncMock(return_value=pts)) as mock_get,
    ):
        body = client.get("/api/sessions/7/telemetry").json()
    assert body == {"enabled": True, "points": pts}
    mock_get.assert_awaited_once_with(7)


def test_soh_history_disabled_when_persistence_off(client):
    with patch("db.get_soh_history", new=AsyncMock(return_value=None)):
        body = client.get("/api/soh-history").json()
    assert body == {"enabled": False, "history": []}


def test_soh_history_returns_points_and_passes_limit(client):
    history = [{"date": "2026-01-01T00:00:00+00:00", "sohPercent": 100}]
    with patch("db.get_soh_history", new=AsyncMock(return_value=history)) as mock_get:
        body = client.get("/api/soh-history?limit=30").json()

    assert body == {"enabled": True, "history": history}
    mock_get.assert_awaited_once_with(30)


# --- energy usage (household vs car) --------------------------------------------


def test_energy_usage_disabled_when_consumption_off(client):
    with patch("octopus.consumption_is_enabled", return_value=False):
        body = client.get("/api/energy-usage").json()
    assert body == {"enabled": False, "slots": [], "totals": None, "date": None}


def test_energy_usage_disabled_when_persistence_off(client):
    with patch("octopus.consumption_is_enabled", return_value=True), \
        patch("db.is_enabled", return_value=False):
        body = client.get("/api/energy-usage").json()
    assert body["enabled"] is False


def test_energy_usage_returns_slots_and_totals(client):
    slots = [
        {"start": "2026-06-01T00:00:00+00:00", "end": "2026-06-01T00:30:00+00:00",
         "importKwh": 1.5, "carKwh": 1.0, "houseKwh": 0.5},
        {"start": "2026-06-01T00:30:00+00:00", "end": "2026-06-01T01:00:00+00:00",
         "importKwh": 0.4, "carKwh": 0.0, "houseKwh": 0.4},
    ]
    with patch("octopus.consumption_is_enabled", return_value=True), \
        patch("db.is_enabled", return_value=True), \
        patch("db.get_grid_consumption", new=AsyncMock(return_value=slots)):
        body = client.get("/api/energy-usage?date=2026-06-01").json()

    assert body["enabled"] is True
    assert body["date"] == "2026-06-01"
    assert body["slots"] == slots
    assert body["totals"] == {
        "importKwh": 1.9, "carKwh": 1.0, "houseKwh": 0.9, "unattributedKwh": 0.0,
    }


def test_energy_usage_defaults_to_yesterday(client):
    import datetime as dt

    captured = {}

    async def fake_get(start, end):
        captured["start"] = start
        captured["end"] = end
        return []

    with patch("octopus.consumption_is_enabled", return_value=True), \
        patch("db.is_enabled", return_value=True), \
        patch("db.get_grid_consumption", new=fake_get):
        body = client.get("/api/energy-usage").json()

    # Default date is yesterday in the configured timezone — compute it through
    # the same logic rather than hard-coding a clock string (CI runs in UTC).
    tz = api._STATS_TZ or dt.timezone.utc
    expected = (dt.datetime.now(tz) - dt.timedelta(days=1)).date()
    assert body["date"] == expected.isoformat()
    # The query window is the local-midnight day for that date (24h span).
    assert captured["end"] - captured["start"] == dt.timedelta(days=1)
    assert captured["start"].date() == expected


def test_energy_usage_rejects_bad_date(client):
    with patch("octopus.consumption_is_enabled", return_value=True), \
        patch("db.is_enabled", return_value=True):
        assert client.get("/api/energy-usage?date=not-a-date").status_code == 400


def test_soh_history_validates_limit(client):
    assert client.get("/api/soh-history?limit=0").status_code == 422
    assert client.get("/api/soh-history?limit=400").status_code == 422


# --- notifications ---------------------------------------------------------------


async def test_notifies_when_charging_finishes():
    store.active_session_key = "session-1"
    store.active_session_id = 42
    snap = StatusSnapshot(
        vehicle_name="IONIQ 5", charger_status="finished", connected=True,
        session_energy_wh=18500.0,
    )
    with patch("ntfy.send", new=AsyncMock()) as mock_notify, \
         patch("db.complete_session", new=AsyncMock()) as complete, \
         patch("db.record_session_event", new=AsyncMock()) as event, \
         patch("api._reconcile_finished_session", new=AsyncMock()) as reconcile:
        await api._maybe_notify_finished("charging", snap)

    mock_notify.assert_awaited_once()
    msg = mock_notify.call_args[0][0]
    assert "IONIQ 5" in msg
    assert "18.5 kWh" in msg
    assert mock_notify.call_args.kwargs["title"] == "Charging finished"
    assert mock_notify.call_args.kwargs["tags"] == "white_check_mark"
    complete.assert_awaited_once_with(
        "session-1", actual_energy_wh=18500.0, end_soc_percent=None
    )
    event.assert_awaited_once()
    assert event.call_args.args[:2] == (42, "charging_finished")
    reconcile.assert_awaited_once_with(snap)


async def test_notifies_when_short_topup_finishes_from_plugged_in():
    # A brief charge can go plugged_in→finished between two polls without ever
    # being sampled as "charging"; energy was added, so it should still notify.
    snap = StatusSnapshot(
        vehicle_name="IONIQ 5", charger_status="finished", connected=True,
        session_energy_wh=2300.0,
    )
    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_notify_finished("plugged_in", snap)
    mock_notify.assert_awaited_once()


async def test_reconcile_finished_session_prices_measured_energy():
    import datetime as dt

    store.active_session_id = 42
    t0 = dt.datetime(2026, 6, 1, tzinfo=dt.timezone.utc)
    rows = [
        (t0, 42, 0.0, 7400.0, "charging", True),
        (t0 + dt.timedelta(minutes=5), 42, 500.0, 7400.0, "finished", True),
    ]
    rates = [{
        "from": t0.isoformat(),
        "to": (t0 + dt.timedelta(minutes=30)).isoformat(),
        "pricePerKwh": 0.10,
    }]
    snap = StatusSnapshot(connected=True, charger_status="finished", session_energy_wh=500.0)
    with patch("db.get_session_attribution_rows", new=AsyncMock(return_value=rows)), \
         patch("db.get_tariff_rates", new=AsyncMock(return_value=rates)), \
         patch("db.record_session_reconciliation", new=AsyncMock()) as record, \
         patch("db.record_session_event", new=AsyncMock()) as event:
        await api._reconcile_finished_session(snap)
    priced = record.call_args.args[1]
    assert priced.energy_wh == 500
    assert priced.cost_minor == 5
    assert priced.coverage == 1.0
    assert record.call_args.kwargs == {"counter_energy_wh": 500.0}
    assert event.call_args.args[1] == "session_reconciled"


@pytest.mark.parametrize(
    "prev,new",
    [
        ("finished", "finished"),  # no transition
        ("unknown", "finished"),   # restart while already finished
        ("charging", "charging"),  # still charging
        ("plugged_in", "finished"),  # never actually charged (0 kWh added)
    ],
)
async def test_no_finish_notification_without_charging_transition(prev, new):
    snap = StatusSnapshot(charger_status=new, connected=True)
    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_notify_finished(prev, snap)
    mock_notify.assert_not_called()


async def test_notifies_when_health_warning_newly_raised():
    prev = StatusSnapshot(vehicle_name="IONIQ 5")  # nothing wrong before
    snap = StatusSnapshot(
        vehicle_name="IONIQ 5", tyre_pressure_warning=True, open_items=["Boot"],
    )
    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_notify_vehicle_health(prev, snap)

    mock_notify.assert_awaited_once()
    msg = mock_notify.call_args[0][0]
    assert "Tyre pressure low" in msg
    assert "Boot open" in msg
    assert mock_notify.call_args.kwargs["tags"] == "warning"


async def test_no_health_notification_when_warning_persists():
    # Same warning in both snapshots — edge-triggered, so it must not repeat.
    prev = StatusSnapshot(tyre_pressure_warning=True, open_items=["Boot"])
    snap = StatusSnapshot(tyre_pressure_warning=True, open_items=["Boot"])
    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_notify_vehicle_health(prev, snap)
    mock_notify.assert_not_called()


async def test_no_health_notification_when_warning_clears_on_unplug():
    # Unplug zeroes the health fields; a True→None/[] change isn't a new warning.
    prev = StatusSnapshot(tyre_pressure_warning=True, open_items=["Boot"])
    snap = StatusSnapshot()  # disconnected: warnings None, open_items []
    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_notify_vehicle_health(prev, snap)
    mock_notify.assert_not_called()


def test_consecutive_failures_count_and_reset():
    store.record_poll_failure("poll_failed")
    store.record_poll_failure("poll_failed")
    assert store.consecutive_poll_failures == 2
    _populate_snapshot()  # a successful poll
    assert store.consecutive_poll_failures == 0


# --- live SOC refresh -----------------------------------------------------------


async def test_live_soc_refreshes_when_charging_and_due(monkeypatch):
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = 60
    store.last_soc_at = None  # no reading yet -> due immediately

    with patch("bluelink.get_vehicle_state", return_value=_vstate(67, range_miles=210)) as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.CHARGING)

    mock_get.assert_called_once()
    assert store.last_soc == 67
    assert store.last_range_miles == 210
    assert store.last_soc_at is not None  # timer reset so the next one waits


async def test_live_soc_skips_when_not_charging(monkeypatch):
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = 60
    store.last_soc_at = None

    with patch("bluelink.get_vehicle_state") as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.PLUGGED_IN)

    mock_get.assert_not_called()
    assert store.last_soc == 60  # untouched


async def test_live_soc_skips_when_recently_read(monkeypatch):
    import time as _time
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = 60
    store.last_soc_at = _time.monotonic()  # just read -> not due

    with patch("bluelink.get_vehicle_state") as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.CHARGING)

    mock_get.assert_not_called()


async def test_live_soc_refreshes_when_reading_is_stale(monkeypatch):
    import time as _time
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = 60
    store.last_soc_at = _time.monotonic() - 3600  # an hour ago -> due

    with patch("bluelink.get_vehicle_state", return_value=_vstate(72)) as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.CHARGING)

    mock_get.assert_called_once()
    assert store.last_soc == 72


async def test_live_soc_disabled_when_interval_zero(monkeypatch):
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 0)
    store.last_soc = 60  # already have a reading -> only the climb path applies
    store.last_soc_at = None

    with patch("bluelink.get_vehicle_state") as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.CHARGING)

    mock_get.assert_not_called()


async def test_live_soc_seeds_when_connected_without_reading(monkeypatch):
    """Restart-mid-session recovery: connected but no held SOC -> fetch once,
    even when not actively charging, so the ring shows the real value instead
    of Ohme's unreliable battery estimate."""
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = None  # lost on restart; prime() won't re-fetch it

    with patch("bluelink.get_vehicle_state", return_value=_vstate(54)) as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.PLUGGED_IN)

    mock_get.assert_called_once()
    assert store.last_soc == 54


async def test_live_soc_no_seed_when_disconnected(monkeypatch):
    """Disconnected with no reading must not fetch — there's nothing plugged in
    to show, and the ring correctly reports unknown."""
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = None

    with patch("bluelink.get_vehicle_state") as mock_get:
        await api._maybe_refresh_live_soc(ChargerStatus.UNPLUGGED)

    mock_get.assert_not_called()


async def test_live_soc_swallows_bluelink_error_keeps_reading(monkeypatch):
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "LIVE_SOC_INTERVAL", 1800)
    store.last_soc = 60
    store.last_soc_at = None

    with patch("bluelink.get_vehicle_state", side_effect=RuntimeError("Bluelink down")):
        await api._maybe_refresh_live_soc(ChargerStatus.CHARGING)  # must not raise

    assert store.last_soc == 60  # prior reading preserved


# --- tariff (Octopus Agile) -----------------------------------------------------


def test_tariff_disabled_returns_enabled_false(client):
    with patch("octopus.is_enabled", return_value=False):
        body = client.get("/api/tariff").json()
    assert body == {"enabled": False, "rates": [], "cheapest": []}


def test_tariff_returns_rates_and_cheapest(client):
    rates = [
        {"from": "2026-06-26T17:00:00Z", "to": "2026-06-26T17:30:00Z", "pricePerKwh": 0.20},
        {"from": "2026-06-26T17:30:00Z", "to": "2026-06-26T18:00:00Z", "pricePerKwh": 0.08},
        {"from": "2026-06-26T18:00:00Z", "to": "2026-06-26T18:30:00Z", "pricePerKwh": 0.15},
    ]
    with patch("octopus.is_enabled", return_value=True), \
         patch("octopus.fetch_rates", new=AsyncMock(return_value=rates)), \
         patch("db.upsert_tariff_rates", new=AsyncMock()) as persist:
        body = client.get("/api/tariff").json()
    assert body["enabled"] is True
    assert len(body["rates"]) == 3
    # Cheapest first, capped at 3.
    assert body["cheapest"][0]["pricePerKwh"] == 0.08
    persist.assert_awaited_once_with(rates)
    assert store.agile_rates == rates


def test_tariff_caches_between_requests(client):
    rates = [{"from": "2026-06-26T17:00:00Z", "to": "2026-06-26T17:30:00Z", "pricePerKwh": 0.1}]
    fetch = AsyncMock(return_value=rates)
    with patch("octopus.is_enabled", return_value=True), patch("octopus.fetch_rates", new=fetch):
        client.get("/api/tariff")
        client.get("/api/tariff")
    fetch.assert_awaited_once()  # second request served from cache


def test_tariff_serves_stale_cache_on_fetch_failure(client):
    good = [{"from": "2026-06-26T17:00:00Z", "to": "2026-06-26T17:30:00Z", "pricePerKwh": 0.1}]
    with patch("octopus.is_enabled", return_value=True):
        with patch("octopus.fetch_rates", new=AsyncMock(return_value=good)):
            client.get("/api/tariff")
        # Force past the cache TTL, then a failing fetch — last good payload wins.
        api._tariff_cache["at"] = 0.0
        with patch("octopus.fetch_rates", new=AsyncMock(return_value=None)):
            body = client.get("/api/tariff").json()
    assert body["rates"] == good


# --- multi-vehicle --------------------------------------------------------------


def test_get_vehicles_lists_and_flags_selected(client, monkeypatch):
    monkeypatch.setattr(config, "HYUNDAI_VEHICLE_ID", "")
    store.set_vehicle_id("car-2")
    fleet = [
        {"id": "car-1", "name": "IONIQ 5", "vin": "VIN1", "model": "IONIQ 5"},
        {"id": "car-2", "name": "Kona", "vin": "VIN2", "model": "Kona"},
    ]
    with patch("bluelink.list_vehicles", return_value=fleet):
        body = client.get("/api/vehicles").json()
    assert body["vehicles"] == fleet
    assert body["selected"] == "car-2"


def test_get_vehicles_502_on_bluelink_error(client):
    with patch("bluelink.list_vehicles", side_effect=RuntimeError("Bluelink down")):
        assert client.get("/api/vehicles").status_code == 502


def test_set_vehicle_updates_store_and_persists(client):
    resp = client.put("/api/settings/vehicle", json={"vehicleId": "car-2"})
    assert resp.status_code == 200
    assert resp.json()["vehicleId"] == "car-2"
    assert store.selected_vehicle_id == "car-2"
    assert settings.load_vehicle_id() == "car-2"  # survives a restart


def test_set_vehicle_clear_with_null(client):
    client.put("/api/settings/vehicle", json={"vehicleId": "car-2"})
    resp = client.put("/api/settings/vehicle", json={"vehicleId": None})
    assert resp.status_code == 200
    assert store.vehicle_id_override is None
    assert settings.load_vehicle_id() is None


def test_selected_vehicle_id_falls_back_to_env(client, monkeypatch):
    monkeypatch.setattr(config, "HYUNDAI_VEHICLE_ID", "env-car")
    store.vehicle_id_override = None
    assert store.selected_vehicle_id == "env-car"
    store.set_vehicle_id("runtime-car")  # runtime override wins
    assert store.selected_vehicle_id == "runtime-car"


# --- telemetry dedupe -----------------------------------------------------------


async def test_telemetry_dedupes_identical_idle_rows():
    snap = StatusSnapshot(connected=False, charger_status="unplugged", battery_percent=None)
    with patch("db.record_telemetry", new=AsyncMock()) as mock_rec:
        await api._maybe_record_telemetry(snap)
        await api._maybe_record_telemetry(snap)  # identical + disconnected -> skipped
    mock_rec.assert_awaited_once()


async def test_telemetry_records_when_idle_state_changes():
    with patch("db.record_telemetry", new=AsyncMock()) as mock_rec:
        await api._maybe_record_telemetry(StatusSnapshot(connected=False, charger_status="unplugged"))
        await api._maybe_record_telemetry(StatusSnapshot(connected=False, charger_status="finished"))
    assert mock_rec.await_count == 2


async def test_telemetry_always_records_while_connected():
    snap = StatusSnapshot(connected=True, charger_status="charging", session_energy_wh=1000.0)
    with patch("db.record_telemetry", new=AsyncMock()) as mock_rec:
        await api._maybe_record_telemetry(snap)
        await api._maybe_record_telemetry(snap)  # identical but connected -> still recorded
    assert mock_rec.await_count == 2


async def test_telemetry_resolves_durable_session_after_restart():
    store.active_session_key = "session-1"
    snap = StatusSnapshot(connected=True, charger_status="charging", session_energy_wh=1000.0)
    with patch("db.get_session_id_by_key", new=AsyncMock(return_value=42)) as lookup, \
         patch("db.record_telemetry", new=AsyncMock()) as record:
        await api._maybe_record_telemetry(snap)
        await api._maybe_record_telemetry(snap)
    lookup.assert_awaited_once_with("session-1")
    assert store.active_session_id == 42
    assert record.await_count == 2
    assert all(call.kwargs["session_id"] == 42 for call in record.await_args_list)


# --- weekly digest --------------------------------------------------------------


import datetime as _dt  # noqa: E402

# 2026-06-01 is a Monday (weekday 0).
_MONDAY_8AM = _dt.datetime(2026, 6, 1, 8, 0)


def test_format_digest_gbp():
    parsed = {
        "currency": "GBP",
        "totals": {
            "energyKwh": 42.1,
            "costTotal": 5.25,
            "savingsVsStandard": 8.4,
            "carbonSavedKgVsGasCar": 12.0,
        },
    }
    msg = api._format_digest(parsed)
    assert "42.1 kWh" in msg
    assert "£5.25" in msg
    assert "£8.40" in msg
    assert "12 kg" in msg
    # One fact per line (header + four bullets) for readability.
    assert msg.startswith("Last 7 days:")
    assert len(msg.splitlines()) == 5


async def test_weekly_digest_sends_on_schedule(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "topic")
    monkeypatch.setattr(config, "WEEKLY_DIGEST_DAY", 0)
    monkeypatch.setattr(config, "WEEKLY_DIGEST_HOUR", 8)
    monkeypatch.setattr(api, "_now_local", lambda: _MONDAY_8AM)

    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_send_weekly_digest(_summary_client())

    mock_notify.assert_awaited_once()
    assert mock_notify.call_args.kwargs["title"] == "Weekly charging summary"
    assert mock_notify.call_args.kwargs["tags"] == "bar_chart"
    assert store.last_digest_date == _MONDAY_8AM.date()  # guards re-send


async def test_weekly_digest_not_resent_same_day(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "topic")
    monkeypatch.setattr(config, "WEEKLY_DIGEST_DAY", 0)
    monkeypatch.setattr(config, "WEEKLY_DIGEST_HOUR", 8)
    monkeypatch.setattr(api, "_now_local", lambda: _MONDAY_8AM)
    store.last_digest_date = _MONDAY_8AM.date()  # already sent today

    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_send_weekly_digest(_summary_client())

    mock_notify.assert_not_called()


async def test_weekly_digest_skips_wrong_day(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "topic")
    monkeypatch.setattr(config, "WEEKLY_DIGEST_DAY", 2)  # Wednesday, but it's Monday
    monkeypatch.setattr(config, "WEEKLY_DIGEST_HOUR", 8)
    monkeypatch.setattr(api, "_now_local", lambda: _MONDAY_8AM)

    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_send_weekly_digest(_summary_client())

    mock_notify.assert_not_called()


async def test_weekly_digest_disabled_without_ntfy(monkeypatch):
    monkeypatch.setattr(config, "NTFY_TOPIC", "")
    monkeypatch.setattr(config, "WEEKLY_DIGEST_DAY", 0)
    monkeypatch.setattr(api, "_now_local", lambda: _MONDAY_8AM)

    with patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await api._maybe_send_weekly_digest(_summary_client())

    mock_notify.assert_not_called()


# --- charge controls -------------------------------------------------------------


@pytest.mark.parametrize(
    "path",
    ["/api/charge/pause", "/api/charge/resume", "/api/refresh"],
)
def test_simple_post_endpoints_require_csrf_header(path):
    # Without X-Requested-With these are forged-able as CORS "simple requests".
    # The guard runs as a dependency, so it rejects before any Ohme work.
    with TestClient(api.app) as bare:
        assert bare.post(path).status_code == 403


@pytest.mark.parametrize(
    "method,path",
    [("post", "/api/charge/pause"), ("post", "/api/charge/resume")],
)
def test_charge_controls_503_when_no_client(client, method, path):
    assert getattr(client, method)(path).status_code == 503


def test_max_charge_503_when_no_client(client):
    assert client.put("/api/charge/max-charge", json={"enabled": True}).status_code == 503


def test_pause_calls_ohme_and_rebuilds_snapshot(client):
    mock_client = _charging_client()
    mock_client.async_pause_charge = AsyncMock(return_value=True)
    mock_client.async_get_charge_session = AsyncMock()
    store.client = mock_client

    resp = client.post("/api/charge/pause")

    assert resp.status_code == 200
    assert resp.json()["ok"] is True
    mock_client.async_pause_charge.assert_awaited_once()
    # Snapshot was re-read so the UI sees the new state immediately.
    mock_client.async_get_charge_session.assert_awaited()
    assert store.status.charger_status == "charging"  # from the mock's status


def test_resume_calls_ohme(client):
    mock_client = _charging_client()
    mock_client.async_resume_charge = AsyncMock(return_value=True)
    mock_client.async_get_charge_session = AsyncMock()
    store.client = mock_client

    resp = client.post("/api/charge/resume")

    assert resp.status_code == 200
    mock_client.async_resume_charge.assert_awaited_once()


@pytest.mark.parametrize("enabled", [True, False])
def test_max_charge_passes_flag_and_reports_state(client, enabled):
    mock_client = _charging_client()
    mock_client.max_charge = enabled  # what Ohme reports after the call
    mock_client.async_max_charge = AsyncMock(return_value=True)
    mock_client.async_get_charge_session = AsyncMock()
    store.client = mock_client

    resp = client.put("/api/charge/max-charge", json={"enabled": enabled})

    assert resp.status_code == 200
    body = resp.json()
    assert body["maxCharge"] is enabled
    mock_client.async_max_charge.assert_awaited_once_with(enabled)


def test_charge_control_502_on_upstream_error(client):
    mock_client = _charging_client()
    mock_client.async_pause_charge = AsyncMock(side_effect=RuntimeError("boom"))
    store.client = mock_client
    assert client.post("/api/charge/pause").status_code == 502


def test_status_reports_max_charge(client):
    store.update(StatusSnapshot(max_charge=True))
    body = client.get("/api/status").json()
    assert body["charger"]["maxCharge"] is True


# --- charge target -------------------------------------------------------------


def test_set_target_updates_store_and_persists(client):
    resp = client.put("/api/settings/target", json={"targetPercent": 65})
    assert resp.status_code == 200
    body = resp.json()
    assert body["targetPercent"] == 65
    assert body["persisted"] is True
    # The runtime override is now in effect…
    assert store.charge_target == 65
    # …and survives a "restart" (reload from the persisted file).
    assert settings.load_target() == 65


def test_set_target_reflected_in_status(client):
    _populate_snapshot()  # ready snapshot with target 80
    client.put("/api/settings/target", json={"targetPercent": 70})
    body = client.get("/api/status").json()
    assert body["config"]["chargeTarget"] == 70
    assert body["charger"]["targetPercent"] == 70


@pytest.mark.parametrize("bad", [0, 9, 101, 150, -5])
def test_set_target_rejects_out_of_range(client, bad):
    resp = client.put("/api/settings/target", json={"targetPercent": bad})
    assert resp.status_code == 422
    assert store.charge_target_override is None


# --- ready-by time --------------------------------------------------------------


def test_set_ready_by_updates_store_and_persists(client):
    resp = client.put("/api/settings/ready-by", json={"readyBy": "07:30"})
    assert resp.status_code == 200
    body = resp.json()
    assert body["readyBy"] == "07:30"
    assert body["persisted"] is True
    assert store.ready_by == "07:30"
    assert settings.load_ready_by() == "07:30"  # survives a restart


def test_set_ready_by_clear_with_null(client):
    client.put("/api/settings/ready-by", json={"readyBy": "06:15"})
    resp = client.put("/api/settings/ready-by", json={"readyBy": None})
    assert resp.status_code == 200
    assert resp.json()["readyBy"] is None
    assert store.ready_by is None
    assert settings.load_ready_by() is None


def test_ready_by_reflected_in_status(client):
    _populate_snapshot()
    client.put("/api/settings/ready-by", json={"readyBy": "08:00"})
    body = client.get("/api/status").json()
    assert body["config"]["readyBy"] == "08:00"


@pytest.mark.parametrize("bad", ["7:30", "24:00", "07:60", "0730", "garbage", "07:30:00"])
def test_set_ready_by_rejects_bad_time(client, bad):
    resp = client.put("/api/settings/ready-by", json={"readyBy": bad})
    assert resp.status_code == 422
    assert store.ready_by is None


def test_set_ready_by_passes_target_time_to_ohme(client):
    mock_client = MagicMock()
    store.client = mock_client
    store.last_soc = 50
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_vehicle_state", return_value=_vstate(55)), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/ready-by", json={"readyBy": "07:30"}).json()

    assert body["applied"] is True
    # The (hour, minute) tuple must be threaded through to Ohme.
    assert mock_set_target.await_args.kwargs["target_time"] == (7, 30)


# --- per-weekday (conditional) targets ------------------------------------------


def test_set_day_targets_updates_store_and_persists(client):
    resp = client.put("/api/settings/day-targets", json={"dayTargets": {"4": 100, "5": 90}})
    assert resp.status_code == 200
    body = resp.json()
    assert body["dayTargets"] == {"4": 100, "5": 90}
    assert body["persisted"] is True
    assert store.day_targets == {4: 100, 5: 90}
    assert settings.load_day_targets() == {4: 100, 5: 90}  # survives a restart


def test_set_day_targets_clear_with_empty(client):
    client.put("/api/settings/day-targets", json={"dayTargets": {"4": 100}})
    resp = client.put("/api/settings/day-targets", json={"dayTargets": {}})
    assert resp.status_code == 200
    assert store.day_targets == {}
    assert settings.load_day_targets() == {}


@pytest.mark.parametrize(
    "bad",
    [{"7": 80}, {"-1": 80}, {"4": 9}, {"4": 101}],
)
def test_set_day_targets_rejects_bad_input(client, bad):
    resp = client.put("/api/settings/day-targets", json={"dayTargets": bad})
    assert resp.status_code == 422
    assert store.day_targets == {}


def test_day_targets_in_status_config(client):
    _populate_snapshot()
    client.put("/api/settings/day-targets", json={"dayTargets": {"6": 95}})
    body = client.get("/api/status").json()
    assert body["config"]["dayTargets"] == {"6": 95}


def test_effective_target_prefers_todays_override(client, monkeypatch):
    # Pin "today" to Friday (weekday 4) so the assertion is deterministic.
    monkeypatch.setattr("state._today_weekday", lambda: 4)
    store.set_charge_target(80)
    store.set_day_targets({4: 100})
    assert store.effective_target == 100
    # A day without an override falls back to the base.
    monkeypatch.setattr("state._today_weekday", lambda: 2)
    assert store.effective_target == 80


def test_plugin_uses_effective_target_in_snapshot(client, monkeypatch):
    monkeypatch.setattr("state._today_weekday", lambda: 5)  # Saturday
    store.set_charge_target(80)
    store.set_day_targets({5: 100})
    store.last_soc = 70
    snap = api.build_snapshot(_charging_client(), connected=True)
    assert snap.target_percent == 100  # Saturday override, not the 80 base


def test_set_target_reapplies_to_ohme_with_fresh_soc(client):
    mock_client = MagicMock()
    store.client = mock_client
    store.last_soc = 50  # SOC recorded at plug-in — stale, the car has charged since
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_vehicle_state", return_value=_vstate(68, range_miles=205)), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 90}).json()

    assert body["applied"] is True
    # The top-up must be computed from the fresh reading, not the plug-in one.
    mock_set_target.assert_awaited_once_with(
        mock_client, current_soc=68, target_percent=90, target_time=None
    )
    assert store.last_soc == 68  # the dashboard now shows the fresh SOC too
    assert store.last_range_miles == 205  # ...and the refreshed range


def test_set_target_falls_back_to_plugin_soc_when_bluelink_fails(client):
    mock_client = MagicMock()
    store.client = mock_client
    store.last_soc = 50
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_vehicle_state", side_effect=RuntimeError("Bluelink down")), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 90}).json()

    assert body["applied"] is True
    mock_set_target.assert_awaited_once_with(
        mock_client, current_soc=50, target_percent=90, target_time=None
    )


def test_set_target_does_not_reapply_when_fresh_soc_at_target(client):
    store.client = MagicMock()
    store.last_soc = 50
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_vehicle_state", return_value=_vstate(85)), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 85}).json()

    assert body["applied"] is False
    mock_set_target.assert_not_called()


def test_set_target_does_not_reapply_when_disconnected(client):
    store.client = MagicMock()
    store.last_soc = 50
    store.status = StatusSnapshot(connected=False)

    with patch("bluelink.get_vehicle_state") as mock_soc, \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 90}).json()

    assert body["applied"] is False
    mock_set_target.assert_not_called()
    # No point waking Bluelink when the car isn't even plugged in.
    mock_soc.assert_not_called()


# --- snapshot builder ----------------------------------------------------------


def _charging_client():
    from ohme.models import ChargerPower, ChargerStatus

    client = MagicMock()
    client.current_vehicle = "IONIQ 5"
    client.battery = 33  # Ohme's unreliable internal estimate
    client.status = ChargerStatus.CHARGING
    client.available = True
    client.max_charge = False
    client.device_info = {"model": "Home Pro"}
    client.power = ChargerPower(watts=7400, amps=32, volts=230)
    client.target_soc = 35  # the top-up amount we sent, NOT the real target
    client.energy = 1000
    client.slots = []
    client.next_slot_start = None
    client.next_slot_end = None
    client.target_time = (0, 0)  # no Ohme ready-by time by default
    return client


def test_build_snapshot_prefers_bluelink_soc_and_config_target():
    import config

    store.last_soc = 70  # real SOC captured from Bluelink at plug-in
    snap = api.build_snapshot(_charging_client(), connected=True)

    assert snap.vehicle_name == "IONIQ 5"
    # Real SOC, not Ohme's 33% estimate.
    assert snap.battery_percent == 70
    # Configured target, not Ohme's 35% top-up value.
    assert snap.target_percent == config.CHARGE_TARGET
    assert snap.charger_status == "charging"
    assert snap.power_watts == 7400
    assert snap.error is None


def test_build_snapshot_falls_back_to_client_battery_before_first_plugin():
    store.last_soc = None
    snap = api.build_snapshot(_charging_client(), connected=True)
    assert snap.battery_percent == 33


def test_build_snapshot_reports_unknown_soc_when_unplugged():
    # Once unplugged, last_soc is cleared. We must not surface Ohme's stale
    # estimate — the SOC is unknown until the next plug-in.
    store.last_soc = None
    snap = api.build_snapshot(_charging_client(), connected=False)
    assert snap.battery_percent is None


def test_build_snapshot_reads_ohme_ready_by():
    client = _charging_client()
    client.target_time = (7, 5)
    assert api.build_snapshot(client, connected=True).ohme_ready_by == "07:05"
    # (0, 0) means no time set.
    client.target_time = (0, 0)
    assert api.build_snapshot(client, connected=True).ohme_ready_by is None


def test_status_ready_by_auto_populates_from_ohme(client):
    # No user override, but Ohme has a configured time — the status should show it.
    store.status = StatusSnapshot(ohme_ready_by="06:30")
    store.ready = True
    store.ready_by = None
    body = client.get("/api/status").json()
    assert body["config"]["readyBy"] == "06:30"
    assert body["config"]["readyByIsManual"] is False


def test_status_ready_by_prefers_user_override(client):
    store.status = StatusSnapshot(ohme_ready_by="06:30")
    store.ready = True
    store.ready_by = "08:00"
    body = client.get("/api/status").json()
    assert body["config"]["readyBy"] == "08:00"
    assert body["config"]["readyByIsManual"] is True


def test_build_snapshot_includes_range_when_connected():
    store.last_range_miles = 180
    assert api.build_snapshot(_charging_client(), connected=True).range_miles == 180
    # Range is the plug-in reading, so it goes stale (None) once unplugged.
    assert api.build_snapshot(_charging_client(), connected=False).range_miles is None


def test_build_snapshot_includes_soh_when_connected():
    store.last_soh_percent = 98
    assert api.build_snapshot(_charging_client(), connected=True).soh_percent == 98
    assert api.build_snapshot(_charging_client(), connected=False).soh_percent is None


def test_build_snapshot_includes_lock_and_location_when_connected():
    store.last_is_locked = True
    store.last_latitude = 51.5
    store.last_longitude = -0.12
    snap = api.build_snapshot(_charging_client(), connected=True)
    assert snap.is_locked is True
    assert (snap.latitude, snap.longitude) == (51.5, -0.12)
    # Cleared once unplugged.
    off = api.build_snapshot(_charging_client(), connected=False)
    assert off.is_locked is None and off.latitude is None


def test_status_exposes_lock_and_location(client):
    store.status = StatusSnapshot(is_locked=False, latitude=51.5, longitude=-0.12)
    store.ready = True
    body = client.get("/api/status").json()
    assert body["vehicle"]["isLocked"] is False
    assert body["vehicle"]["location"] == {"latitude": 51.5, "longitude": -0.12}


def test_status_location_null_without_coords(client):
    store.status = StatusSnapshot(is_locked=True, latitude=None, longitude=None)
    store.ready = True
    body = client.get("/api/status").json()
    assert body["vehicle"]["location"] is None
    assert body["vehicle"]["isLocked"] is True


def _slot(energy, end=None):
    s = MagicMock()
    s.energy = energy
    s.end = end
    s.to_dict = lambda: {"energy": energy}
    return s


def test_cache_avg_price_sets_and_ignores_zero():
    api._cache_avg_price({"currency": "GBP", "totals": {"averageKwhPrice": 0.0728}})
    assert store.avg_price_per_kwh == 0.0728
    assert store.price_currency == "GBP"
    # A zero/absent price must not overwrite a known one.
    api._cache_avg_price({"currency": "GBP", "totals": {"averageKwhPrice": 0}})
    assert store.avg_price_per_kwh == 0.0728


def test_build_snapshot_projects_session_cost():
    import datetime as dt

    client = _charging_client()
    client.slots = [
        _slot(10.0, dt.datetime(2026, 6, 13, 4, 0, tzinfo=dt.timezone.utc)),
        _slot(8.0, dt.datetime(2026, 6, 13, 6, 0, tzinfo=dt.timezone.utc)),
    ]
    store.avg_price_per_kwh = 0.10
    store.price_currency = "GBP"
    snap = api.build_snapshot(client, connected=True)
    assert snap.planned_energy_kwh == 18.0
    assert snap.projected_cost == 1.8  # 18 kWh * £0.10
    assert snap.projected_cost_currency == "GBP"
    assert snap.projected_cost_method == "average"  # no Agile rates cached


def test_build_snapshot_prices_slots_against_agile_rates():
    import datetime as dt

    base = dt.datetime(2026, 6, 13, 2, 0, tzinfo=dt.timezone.utc)

    def slot(energy, start_h, end_h):
        s = MagicMock()
        s.energy = energy
        s.start = base.replace(hour=start_h)
        s.end = base.replace(hour=end_h)
        s.to_dict = lambda: {"energy": energy}
        return s

    client = _charging_client()
    # Two 1h slots, each priced against its own half-of-the-window Agile rate.
    client.slots = [slot(10.0, 2, 3), slot(10.0, 3, 4)]
    store.agile_rates = [
        {"from": base.replace(hour=2).isoformat(), "to": base.replace(hour=3).isoformat(), "pricePerKwh": 0.05},
        {"from": base.replace(hour=3).isoformat(), "to": base.replace(hour=4).isoformat(), "pricePerKwh": 0.25},
    ]
    store.avg_price_per_kwh = 0.10  # would give £2.00 — Agile must win
    snap = api.build_snapshot(client, connected=True)
    assert snap.projected_cost == 3.0  # 10*0.05 + 10*0.25
    assert snap.projected_cost_method == "agile"
    assert snap.projected_cost_currency == "GBP"


def test_build_snapshot_no_cost_without_price():
    client = _charging_client()
    client.slots = [_slot(10.0)]
    store.avg_price_per_kwh = None
    snap = api.build_snapshot(client, connected=True)
    assert snap.planned_energy_kwh == 10.0  # energy still reported
    assert snap.projected_cost is None  # but no estimate without a price


def test_build_snapshot_no_cost_when_disconnected():
    client = _charging_client()
    client.slots = [_slot(10.0)]
    store.avg_price_per_kwh = 0.10
    snap = api.build_snapshot(client, connected=False)
    assert snap.projected_cost is None
    assert snap.planned_energy_kwh == 0.0


def test_build_snapshot_projects_finish_from_last_slot_end():
    import datetime as dt

    client = _charging_client()
    early, late = MagicMock(), MagicMock()
    early.energy = late.energy = 5.0
    early.end = dt.datetime(2026, 6, 13, 4, 30, tzinfo=dt.timezone.utc)
    late.end = dt.datetime(2026, 6, 13, 6, 30, tzinfo=dt.timezone.utc)
    early.to_dict.return_value = {}
    late.to_dict.return_value = {}
    # Deliberately out of order: the finish is the latest end, not the last entry.
    client.slots = [late, early]

    snap = api.build_snapshot(client, connected=True)

    assert snap.projected_finish == "2026-06-13T06:30:00+00:00"


def test_build_snapshot_no_projected_finish_without_slots_or_when_disconnected():
    assert api.build_snapshot(_charging_client(), connected=True).projected_finish is None
    client = _charging_client()
    slot = MagicMock()
    slot.to_dict.return_value = {}
    client.slots = [slot]
    assert api.build_snapshot(client, connected=False).projected_finish is None


def test_build_snapshot_with_error():
    snap = api.build_snapshot(MagicMock(), connected=False, error="poll_failed")
    assert snap.error == "poll_failed"
    assert snap.updated_at is not None


# --- access-log filter ---------------------------------------------------------


def _access_record(method: str, path: str, status: int) -> logging.LogRecord:
    return logging.LogRecord(
        name="uvicorn.access",
        level=logging.INFO,
        pathname=__file__,
        lineno=1,
        msg='%s - "%s %s HTTP/%s" %d',
        args=("172.0.0.1:1234", method, path, "1.1", status),
        exc_info=None,
    )


@pytest.mark.parametrize("path", ["/api/health", "/api/status", "/api/schedule", "/api/statistics"])
def test_quiet_filter_drops_successful_polling_gets(path):
    assert api._quiet_access_filter.filter(_access_record("GET", path, 200)) is False


def test_quiet_filter_keeps_polling_endpoint_errors():
    assert api._quiet_access_filter.filter(_access_record("GET", "/api/health", 503)) is True


def test_quiet_filter_keeps_other_paths_and_methods():
    assert api._quiet_access_filter.filter(_access_record("GET", "/api/other", 200)) is True
    assert api._quiet_access_filter.filter(_access_record("POST", "/api/status", 200)) is True


def test_quiet_filter_ignores_query_string():
    assert api._quiet_access_filter.filter(_access_record("GET", "/api/statistics?days=7", 200)) is False


def test_quiet_filter_installed_on_startup(client):
    assert api._quiet_access_filter in logging.getLogger("uvicorn.access").filters


def test_next_poll_delay_baseline_when_healthy(monkeypatch):
    monkeypatch.setattr(config, "POLL_INTERVAL", 180)
    assert api._next_poll_delay(0) == 180
    # Defensive: a negative count is also treated as healthy.
    assert api._next_poll_delay(-1) == 180


def test_next_poll_delay_grows_exponentially_then_caps(monkeypatch):
    monkeypatch.setattr(config, "POLL_INTERVAL", 180)
    monkeypatch.setattr(config, "MAX_POLL_BACKOFF", 1800)
    assert api._next_poll_delay(1) == 180   # first failure: still one interval
    assert api._next_poll_delay(2) == 360   # 180 * 2
    assert api._next_poll_delay(3) == 720   # 180 * 4
    assert api._next_poll_delay(4) == 1440  # 180 * 8
    assert api._next_poll_delay(5) == 1800  # 180 * 16 -> capped
    assert api._next_poll_delay(50) == 1800  # long outage stays at the cap
