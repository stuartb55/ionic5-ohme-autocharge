"""Tests for the FastAPI backend.

Polling is disabled (see conftest) so the app starts without touching Ohme. We
drive the read endpoints by injecting a snapshot into ``state.store`` and the
statistics endpoint by mocking the client's ``async_get_charge_summary``.
"""

from unittest.mock import AsyncMock, MagicMock

import pytest
from fastapi.testclient import TestClient

import api
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
    api._summary_cache.update(key=None, value=None, at=0.0)
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
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(
        return_value={
            "granularity": "DAY",
            "totalStats": {
                "energyChargedTotalWh": 42000,
                "costStats": {
                    "moneyCostTotal": {"currencyCode": "GBP", "amount": "5.25"},
                    "moneySavedVsStandardTariff": {"currencyCode": "GBP", "amount": "8.40"},
                    "averageKwhPrice": {"currencyCode": "GBP", "amount": "0.125"},
                },
                "carbonStats": {"carbonSavedVsGasCarGrams": 12000},
            },
            "stats": [
                {
                    "startTime": 1748822400000,
                    "energyChargedTotalWh": 18500,
                    "costStats": {
                        "moneyCostTotal": {"currencyCode": "GBP", "amount": "2.30"},
                        "moneySavedVsStandardTariff": {"currencyCode": "GBP", "amount": "3.70"},
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
    assert body["totals"]["savingsVsStandard"] == 8.4
    assert body["totals"]["carbonSavedKgVsGasCar"] == 12.0
    assert len(body["daily"]) == 1
    assert body["daily"][0]["energyKwh"] == 18.5
    assert body["daily"][0]["savings"] == 3.7


def test_statistics_validates_days_range(client):
    store.client = MagicMock()
    assert client.get("/api/statistics?days=0").status_code == 422
    assert client.get("/api/statistics?days=1000").status_code == 422


def test_statistics_502_on_upstream_error(client):
    mock_client = MagicMock()
    mock_client.async_get_charge_summary = AsyncMock(side_effect=RuntimeError("boom"))
    store.client = mock_client
    assert client.get("/api/statistics").status_code == 502


# --- snapshot builder ----------------------------------------------------------


def _charging_client():
    from ohme.models import ChargerPower, ChargerStatus

    client = MagicMock()
    client.current_vehicle = "IONIQ 5"
    client.battery = 33  # Ohme's unreliable internal estimate
    client.status = ChargerStatus.CHARGING
    client.available = True
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
