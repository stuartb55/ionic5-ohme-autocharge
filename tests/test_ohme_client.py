import asyncio
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from ohme import ChargerStatus

import config
import ohme_client


def _mock_client(status: ChargerStatus = ChargerStatus.UNPLUGGED) -> MagicMock:
    client = MagicMock()
    client.async_get_charge_session = AsyncMock()
    client.async_update_device_info = AsyncMock()
    client.async_set_state_of_charge = AsyncMock()
    client.async_set_target = AsyncMock()
    client.status = status
    return client


async def test_get_charger_status_returns_status():
    client = _mock_client(ChargerStatus.CHARGING)
    assert await ohme_client.get_charger_status(client) == ChargerStatus.CHARGING


async def test_get_charger_status_defaults_to_unplugged_on_malformed_session():
    # The library's `status` property raises KeyError when the charge session
    # has no "mode" key; we map that to UNPLUGGED.
    client = _mock_client()
    type(client).status = PropertyMock(side_effect=KeyError("mode"))
    assert await ohme_client.get_charger_status(client) == ChargerStatus.UNPLUGGED


async def test_get_charger_status_calls_get_charge_session():
    client = _mock_client(ChargerStatus.PAUSED)
    await ohme_client.get_charger_status(client)
    client.async_get_charge_session.assert_called_once()


async def test_get_charger_status_times_out(monkeypatch):
    """A hung Ohme refresh must not stall the poll loop — wait_for raises."""
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.05)
    client = _mock_client()

    async def slow():
        await asyncio.sleep(0.5)

    client.async_get_charge_session = slow
    with pytest.raises(TimeoutError):
        await ohme_client.get_charger_status(client)


async def test_make_client_times_out_login_and_closes_partial_client(monkeypatch):
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.01)
    client = _mock_client()
    client.close = AsyncMock()

    async def hung_login():
        await asyncio.sleep(1)

    client.async_login = hung_login
    monkeypatch.setattr(ohme_client, "OhmeApiClient", lambda *_: client)

    with pytest.raises(TimeoutError):
        await ohme_client.make_client()

    client.close.assert_awaited_once()


@pytest.mark.parametrize(
    "status",
    [
        ChargerStatus.PENDING_APPROVAL,
        ChargerStatus.CHARGING,
        ChargerStatus.PLUGGED_IN,
        ChargerStatus.PAUSED,
        ChargerStatus.FINISHED,
    ],
)
def test_is_connected_true_for_plugged_in_statuses(status):
    assert ohme_client.is_connected(status) is True


def test_is_connected_false_for_unplugged():
    assert ohme_client.is_connected(ChargerStatus.UNPLUGGED) is False


def test_is_charging_only_true_when_charging():
    assert ohme_client.is_charging(ChargerStatus.CHARGING) is True
    for status in (
        ChargerStatus.UNPLUGGED,
        ChargerStatus.PLUGGED_IN,
        ChargerStatus.PAUSED,
        ChargerStatus.FINISHED,
        ChargerStatus.PENDING_APPROVAL,
    ):
        assert ohme_client.is_charging(status) is False


async def test_set_target_calls_methods_in_correct_order():
    client = _mock_client()
    call_order = []
    client.async_update_device_info.side_effect = lambda: call_order.append("update_device_info")
    client.async_get_charge_session.side_effect = lambda: call_order.append("get_charge_session")
    client.async_set_target.side_effect = lambda **_: call_order.append("set_target")

    await ohme_client.set_target(client, current_soc=62, target_percent=80)

    assert call_order == ["update_device_info", "get_charge_session", "set_target", "get_charge_session"]


async def test_set_target_passes_correct_values():
    client = _mock_client()
    await ohme_client.set_target(client, current_soc=55, target_percent=80)
    # top-up = 80 - 55; no ready-by time set
    client.async_set_target.assert_called_once_with(target_percent=25, target_time=None)
    client.async_set_state_of_charge.assert_not_called()


async def test_set_target_passes_ready_by_time():
    client = _mock_client()
    await ohme_client.set_target(client, current_soc=55, target_percent=80, target_time=(7, 30))
    client.async_set_target.assert_called_once_with(target_percent=25, target_time=(7, 30))


async def test_set_target_clamps_a_lower_restored_target_to_zero_topup():
    client = _mock_client()
    await ohme_client.set_target(client, current_soc=90, target_percent=80)
    client.async_set_target.assert_called_once_with(target_percent=0, target_time=None)


async def test_set_target_times_out_a_hung_write(monkeypatch):
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.01)
    client = _mock_client()

    async def hung_write(**_):
        await asyncio.sleep(1)

    client.async_set_target = hung_write
    with pytest.raises(TimeoutError):
        await ohme_client.set_target(client, current_soc=50, target_percent=80)


async def test_set_target_reports_partial_write_when_refresh_hangs(monkeypatch):
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.01)
    client = _mock_client()
    refreshes = 0

    async def refresh():
        nonlocal refreshes
        refreshes += 1
        if refreshes == 2:
            await asyncio.sleep(1)

    client.async_get_charge_session = refresh
    with pytest.raises(TimeoutError):
        await ohme_client.set_target(client, current_soc=50, target_percent=80)

    client.async_set_target.assert_awaited_once()


async def test_charge_summary_is_bounded(monkeypatch):
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.01)
    client = _mock_client()

    async def hung_summary(**_):
        await asyncio.sleep(1)

    client.async_get_charge_summary = hung_summary
    with pytest.raises(TimeoutError):
        await ohme_client.get_charge_summary(client, start_ts=1, end_ts=2)
