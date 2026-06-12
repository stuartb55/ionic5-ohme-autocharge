import asyncio
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import config
from main import handle_plugin_event, run_loop


def _mock_ohme_client(slots=None):
    client = MagicMock()
    client.slots = slots or []
    return client


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
    msg = mock_notify.call_args[0][0]
    assert "62%" in msg
    assert "80%" in msg
    assert "Charge schedule" not in msg  # no slots on this client


async def test_notification_includes_charge_schedule_when_slots_available(monkeypatch):
    from unittest.mock import MagicMock as MM
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    slot = MM()
    slot.__str__ = lambda self: "01:00-03:30"
    client = _mock_ohme_client(slots=[slot])

    with patch("bluelink.get_battery_percentage", return_value=62), \
         patch("ohme_client.set_target", new=AsyncMock()), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await handle_plugin_event(client)

    msg = mock_notify.call_args[0][0]
    assert "Charge schedule: 01:00-03:30" in msg


async def test_records_session_and_schedule_when_db_enabled(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"
    client.next_slot_start = None
    client.next_slot_end = None

    with patch("bluelink.get_battery_percentage", return_value=62), \
         patch("ohme_client.set_target", new=AsyncMock()), \
         patch("ntfy.send", new=AsyncMock()), \
         patch("db.is_enabled", return_value=True), \
         patch("db.record_session", new=AsyncMock(return_value=7)) as mock_session, \
         patch("db.record_schedule", new=AsyncMock()) as mock_schedule:
        result = await handle_plugin_event(client)

    assert result is True
    mock_session.assert_awaited_once_with(
        vehicle_name="IONIQ 5", soc_percent=62, target_percent=80, topup_percent=18, action="configured"
    )
    mock_schedule.assert_awaited_once()
    assert mock_schedule.call_args.kwargs["session_id"] == 7


async def test_records_skipped_session_when_already_at_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"

    with patch("bluelink.get_battery_percentage", return_value=90), \
         patch("db.is_enabled", return_value=True), \
         patch("db.record_session", new=AsyncMock(return_value=1)) as mock_session:
        result = await handle_plugin_event(client)

    assert result is True
    mock_session.assert_awaited_once_with(
        vehicle_name="IONIQ 5", soc_percent=90, target_percent=80, topup_percent=0, action="skipped_at_target"
    )


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


# --- run_loop startup behaviour ---

def _make_loop_client():
    """Return a mock Ohme client for run_loop tests."""
    client = MagicMock()
    client.close = AsyncMock()
    client.async_update_device_info = AsyncMock()
    return client


async def test_reconfigures_on_restart_when_already_connected(monkeypatch):
    """Container restart mid-charge should always reconfigure Ohme on the first poll."""
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _make_loop_client()

    with patch("ohme_client.make_client", new=AsyncMock(return_value=client)), \
         patch("ohme_client.is_connected", side_effect=lambda m: m != "DISCONNECTED"), \
         patch("ohme_client.get_session_mode", new=AsyncMock(return_value="SMART_CHARGE")), \
         patch("main.handle_plugin_event", new=AsyncMock(return_value=True)) as mock_handle, \
         patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
        try:
            await run_loop()
        except asyncio.CancelledError:
            pass

    mock_handle.assert_called_once()
    # Vehicle name must be available before the first plug-in event is recorded.
    client.async_update_device_info.assert_awaited_once()
