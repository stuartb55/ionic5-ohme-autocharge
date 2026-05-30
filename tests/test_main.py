from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import config
from main import handle_plugin_event


def _mock_ohme_client():
    return MagicMock()


async def test_returns_false_when_bluelink_fails():
    with patch("bluelink.get_battery_percentage", side_effect=RuntimeError("No vehicles found")):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is False


async def test_returns_true_when_soc_already_at_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    with patch("bluelink.get_battery_percentage", return_value=80):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is True


async def test_returns_true_when_soc_above_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    with patch("bluelink.get_battery_percentage", return_value=95):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is True


async def test_sets_ohme_target_and_sends_notification_when_below_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()

    with patch("bluelink.get_battery_percentage", return_value=62), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target, \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        result = await handle_plugin_event(client)

    assert result is True
    mock_set_target.assert_called_once_with(client, current_soc=62, target_percent=80)
    mock_notify.assert_called_once()
    assert "62%" in mock_notify.call_args[0][0]
    assert "80%" in mock_notify.call_args[0][0]


async def test_returns_false_when_ohme_fails_and_does_not_notify(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)

    with patch("bluelink.get_battery_percentage", return_value=62), \
         patch("ohme_client.set_target", new=AsyncMock(side_effect=Exception("Ohme API error"))), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        result = await handle_plugin_event(_mock_ohme_client())

    assert result is False
    mock_notify.assert_not_called()


async def test_no_ohme_call_when_soc_at_or_above_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)

    with patch("bluelink.get_battery_percentage", return_value=80), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        await handle_plugin_event(_mock_ohme_client())

    mock_set_target.assert_not_called()
