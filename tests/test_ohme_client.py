from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest
from ohme import ChargerStatus

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
    client.async_set_target.assert_called_once_with(target_percent=25)  # top-up = 80 - 55
    client.async_set_state_of_charge.assert_not_called()
