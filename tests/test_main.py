import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import bluelink
import config
import settings
from main import handle_plugin_event, run_loop, run_once
from state import store


def _vstate(soc, *, range_miles=150, odometer_miles=10000, soh_percent=None):
    """Build a Bluelink VehicleState for patching bluelink.get_vehicle_state."""
    return bluelink.VehicleState(
        soc=soc, range_miles=range_miles, odometer_miles=odometer_miles, soh_percent=soh_percent
    )


def _mock_ohme_client(slots=None):
    client = MagicMock()
    client.slots = slots or []
    return client


@pytest.fixture(autouse=True)
def _reset_session_state():
    """Plug-in handling mutates the shared store and the persisted session
    marker; keep tests independent."""
    store.clear_soc()
    settings.save_session_active(False)
    yield
    store.clear_soc()
    settings.save_session_active(False)


async def test_returns_false_when_bluelink_fails():
    with patch("bluelink.get_vehicle_state", side_effect=RuntimeError("No vehicles found")):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is False


async def test_returns_false_when_bluelink_times_out(monkeypatch):
    """A hung Bluelink read is treated as a failed plug-in (skip, retry next poll)."""
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.05)

    def slow(_vehicle_id):
        import time
        time.sleep(0.3)
        return _vstate(50)

    monkeypatch.setattr(bluelink, "get_vehicle_state", slow)
    with patch("ntfy.send", new=AsyncMock()):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is False


async def test_returns_true_when_soc_already_at_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    with patch("bluelink.get_vehicle_state", return_value=_vstate(80)):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is True


async def test_returns_true_when_soc_above_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    with patch("bluelink.get_vehicle_state", return_value=_vstate(95)):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is True


async def test_sets_ohme_target_and_sends_notification_when_below_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()

    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target, \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        result = await handle_plugin_event(client)

    assert result is True
    mock_set_target.assert_called_once_with(
        client, current_soc=62, target_percent=80, target_time=None
    )
    mock_notify.assert_called_once()
    msg = mock_notify.call_args[0][0]
    assert "62%" in msg
    assert "80%" in msg
    assert "Schedule" not in msg  # no slots on this client
    assert mock_notify.call_args.kwargs["tags"] == "electric_plug"


async def test_notification_includes_charge_schedule_when_slots_available(monkeypatch):
    from unittest.mock import MagicMock as MM
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    slot = MM()
    slot.__str__ = lambda self: "01:00-03:30"
    client = _mock_ohme_client(slots=[slot])

    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock()), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await handle_plugin_event(client)

    msg = mock_notify.call_args[0][0]
    assert "Schedule: 01:00-03:30" in msg
    # Each fact on its own line for readability.
    assert "62% → 80%" in msg.splitlines()[0]


async def test_records_session_and_schedule_when_db_enabled(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"
    client.next_slot_start = None
    client.next_slot_end = None

    with patch("bluelink.get_vehicle_state", return_value=_vstate(62, soh_percent=98)), \
         patch("ohme_client.set_target", new=AsyncMock()), \
         patch("ntfy.send", new=AsyncMock()), \
         patch("db.is_enabled", return_value=True), \
         patch("db.record_session", new=AsyncMock(return_value=7)) as mock_session, \
         patch("db.record_schedule", new=AsyncMock()) as mock_schedule:
        plugged_at = dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc)
        result = await handle_plugin_event(
            client, session_key="session-1", plugged_in_at=plugged_at
        )

    assert result is True
    mock_session.assert_awaited_once_with(
        vehicle_name="IONIQ 5", soc_percent=62, target_percent=80, topup_percent=18,
        action="configured", odometer_miles=10000, soh_percent=98,
        session_key="session-1", vehicle_id=None, vin=None, charger_id=None,
        source_observed_at=None, plugged_in_at=plugged_at,
    )
    mock_schedule.assert_awaited_once()
    assert mock_schedule.call_args.kwargs["session_id"] == 7


async def test_records_skipped_session_when_already_at_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"

    with patch("bluelink.get_vehicle_state", return_value=_vstate(90, odometer_miles=12000, soh_percent=97)), \
         patch("db.is_enabled", return_value=True), \
         patch("db.record_session", new=AsyncMock(return_value=1)) as mock_session:
        plugged_at = dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc)
        result = await handle_plugin_event(
            client, session_key="session-2", plugged_in_at=plugged_at
        )

    assert result is True
    mock_session.assert_awaited_once_with(
        vehicle_name="IONIQ 5", soc_percent=90, target_percent=80, topup_percent=0,
        action="skipped_at_target", odometer_miles=12000, soh_percent=97,
        session_key="session-2", vehicle_id=None, vin=None, charger_id=None,
        source_observed_at=None, plugged_in_at=plugged_at,
    )


async def test_returns_false_when_ohme_fails_and_sends_only_failure_alert(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)

    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock(side_effect=Exception("Ohme API error"))), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        result = await handle_plugin_event(_mock_ohme_client())

    assert result is False
    # The "plugged in → target set" success message must NOT be sent; the only
    # notification is the high-priority failure alert.
    mock_notify.assert_awaited_once()
    assert "plugged in" not in mock_notify.call_args[0][0]
    assert mock_notify.call_args.kwargs["priority"] == "high"


async def test_no_ohme_call_when_soc_at_or_above_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)

    with patch("bluelink.get_vehicle_state", return_value=_vstate(80)), \
         patch("ohme_client.set_target", new=AsyncMock()) as mock_set_target:
        await handle_plugin_event(_mock_ohme_client())

    mock_set_target.assert_not_called()


# --- plug-in failure notifications ---


async def test_bluelink_failure_notifies_once_per_session():
    with patch("bluelink.get_vehicle_state", side_effect=RuntimeError("down")), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        # The poll loop retries every interval; only the first failure alerts.
        await handle_plugin_event(_mock_ohme_client())
        await handle_plugin_event(_mock_ohme_client())

    mock_notify.assert_awaited_once()
    assert mock_notify.call_args.kwargs["priority"] == "high"


async def test_ohme_failure_notifies_once_per_session(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock(side_effect=Exception("boom"))), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        await handle_plugin_event(_mock_ohme_client())
        await handle_plugin_event(_mock_ohme_client())

    mock_notify.assert_awaited_once()


async def test_successful_handling_resets_failure_notice(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    store.plugin_failure_notified = True  # a previous attempt alerted

    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock()), \
         patch("ntfy.send", new=AsyncMock()):
        result = await handle_plugin_event(_mock_ohme_client())

    assert result is True
    assert store.plugin_failure_notified is False


# --- run_loop startup behaviour ---

def _make_loop_client():
    """Return a mock Ohme client for run_loop tests."""
    client = MagicMock()
    client.close = AsyncMock()
    client.async_update_device_info = AsyncMock()
    return client


async def test_restart_mid_handled_session_does_not_re_handle(monkeypatch):
    """A container restart while the car is mid-charge must NOT re-record or
    re-notify: the session was already handled before the restart (persisted
    sessionActive=True), so handle_plugin_event is never called."""
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    settings.save_session_active(True)  # session was handled before the restart
    client = _make_loop_client()

    from ohme import ChargerStatus

    with patch("ohme_client.make_client", new=AsyncMock(return_value=client)), \
         patch("ohme_client.get_charger_status", new=AsyncMock(return_value=ChargerStatus.CHARGING)), \
         patch("main.handle_plugin_event", new=AsyncMock(return_value=True)) as mock_handle, \
         patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
        try:
            await run_loop()
        except asyncio.CancelledError:
            pass

    mock_handle.assert_not_called()


async def test_connected_on_startup_without_prior_session_is_handled(monkeypatch):
    """When the car was plugged in while the container was down (no persisted
    sessionActive), the session was never configured — so it must be handled on
    the first poll."""
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    settings.save_session_active(False)  # nothing handled before startup
    client = _make_loop_client()

    from ohme import ChargerStatus

    with patch("ohme_client.make_client", new=AsyncMock(return_value=client)), \
         patch("ohme_client.get_charger_status", new=AsyncMock(return_value=ChargerStatus.CHARGING)), \
         patch("main.handle_plugin_event", new=AsyncMock(return_value=True)) as mock_handle, \
         patch("asyncio.sleep", side_effect=asyncio.CancelledError()):
        try:
            await run_loop()
        except asyncio.CancelledError:
            pass

    mock_handle.assert_called_once()
    # Vehicle name must be available before the first plug-in event is recorded.
    client.async_update_device_info.assert_awaited_once()
    # A handled session is persisted so a later restart won't re-record it.
    assert settings.load_session_active() is True


# --- run_once exit code ---


@pytest.mark.parametrize("handled,expected_code", [(True, 0), (False, 1)])
async def test_run_once_exit_code_reflects_outcome(handled, expected_code):
    """CI/smoke callers rely on the exit code, so a failed one-shot must be non-zero."""
    client = _make_loop_client()

    with patch("ohme_client.make_client", new=AsyncMock(return_value=client)), \
         patch("main.handle_plugin_event", new=AsyncMock(return_value=handled)):
        assert await run_once() == expected_code

    client.close.assert_awaited()


async def test_unplug_clears_recorded_soc(monkeypatch):
    """The plug-in SOC must be forgotten on unplug — it's stale once the car drives away."""
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _make_loop_client()
    store.record_soc(62)

    from ohme import ChargerStatus

    # Startup + poll 1: connected (plug-in handled); poll 2: unplugged.
    statuses = AsyncMock(
        side_effect=[ChargerStatus.CHARGING, ChargerStatus.CHARGING, ChargerStatus.UNPLUGGED]
    )
    sleeps = AsyncMock(side_effect=[None, asyncio.CancelledError()])

    with patch("ohme_client.make_client", new=AsyncMock(return_value=client)), \
         patch("ohme_client.get_charger_status", new=statuses), \
         patch("main.handle_plugin_event", new=AsyncMock(return_value=True)), \
         patch("asyncio.sleep", new=sleeps):
        try:
            await run_loop()
        except asyncio.CancelledError:
            pass

    assert store.last_soc is None
    # Unplug must also clear the persisted session marker so the next plug-in
    # (after a restart) is handled afresh.
    assert settings.load_session_active() is False


# --- persisted session marker ---


def test_session_active_round_trip():
    """save/load round-trips, and an unset marker reads as False (not handled)."""
    settings.save_session_active(False)
    assert settings.load_session_active() is False
    assert settings.save_session_active(True) is True
    assert settings.load_session_active() is True
    settings.save_session_active(False)
    assert settings.load_session_active() is False
