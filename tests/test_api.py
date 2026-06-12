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
import settings
from state import StatusSnapshot, store


@pytest.fixture
def client():
    with TestClient(api.app) as c:
        yield c


@pytest.fixture(autouse=True)
def reset_state():
    store.status = StatusSnapshot()
    store.client = None
    store.ready = False
    store.last_soc = None
    store.charge_target_override = None
    store.last_poll_error = None
    api._summary_cache.update(key=None, value=None, at=0.0)
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
            updated_at="2026-06-02T00:00:00+01:00",
        )
    )


def test_health_ok(client):
    resp = client.get("/api/health")
    assert resp.status_code == 200
    assert resp.json()["status"] == "ok"


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
    assert body["config"]["chargeTarget"] == 80
    assert body["ready"] is True


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


# --- charge controls -------------------------------------------------------------


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


def test_set_target_reapplies_to_ohme_with_fresh_soc(client):
    mock_client = MagicMock()
    store.client = mock_client
    store.last_soc = 50  # SOC recorded at plug-in — stale, the car has charged since
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_battery_percentage", return_value=68), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 90}).json()

    assert body["applied"] is True
    # The top-up must be computed from the fresh reading, not the plug-in one.
    mock_set_target.assert_awaited_once_with(mock_client, current_soc=68, target_percent=90)
    assert store.last_soc == 68  # the dashboard now shows the fresh SOC too


def test_set_target_falls_back_to_plugin_soc_when_bluelink_fails(client):
    mock_client = MagicMock()
    store.client = mock_client
    store.last_soc = 50
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_battery_percentage", side_effect=RuntimeError("Bluelink down")), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 90}).json()

    assert body["applied"] is True
    mock_set_target.assert_awaited_once_with(mock_client, current_soc=50, target_percent=90)


def test_set_target_does_not_reapply_when_fresh_soc_at_target(client):
    store.client = MagicMock()
    store.last_soc = 50
    store.status = StatusSnapshot(connected=True)
    store.ready = True

    with patch("bluelink.get_battery_percentage", return_value=85), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        body = client.put("/api/settings/target", json={"targetPercent": 85}).json()

    assert body["applied"] is False
    mock_set_target.assert_not_called()


def test_set_target_does_not_reapply_when_disconnected(client):
    store.client = MagicMock()
    store.last_soc = 50
    store.status = StatusSnapshot(connected=False)

    with patch("bluelink.get_battery_percentage") as mock_soc, \
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
