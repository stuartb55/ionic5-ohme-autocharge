from unittest.mock import AsyncMock, MagicMock
import pytest
import ohme_client


def _mock_client(mode: str = "DISCONNECTED") -> MagicMock:
    client = MagicMock()
    client.async_get_charge_session = AsyncMock()
    client.async_update_device_info = AsyncMock()
    client.async_set_state_of_charge = AsyncMock()
    client.async_set_target = AsyncMock()
    client._charge_session = {"mode": mode}
    return client


async def test_get_session_mode_returns_mode():
    client = _mock_client("SMART_CHARGE")
    assert await ohme_client.get_session_mode(client) == "SMART_CHARGE"


async def test_get_session_mode_defaults_to_disconnected_when_key_missing():
    client = _mock_client()
    client._charge_session = {}
    assert await ohme_client.get_session_mode(client) == "DISCONNECTED"


async def test_get_session_mode_calls_get_charge_session():
    client = _mock_client("STOPPED")
    await ohme_client.get_session_mode(client)
    client.async_get_charge_session.assert_called_once()


@pytest.mark.parametrize("mode", ["SMART_CHARGE", "MAX_CHARGE", "STOPPED", "FINISHED_CHARGE", "PENDING_APPROVAL"])
def test_is_connected_true_for_active_modes(mode):
    assert ohme_client.is_connected(mode) is True


def test_is_connected_false_for_disconnected():
    assert ohme_client.is_connected("DISCONNECTED") is False


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
