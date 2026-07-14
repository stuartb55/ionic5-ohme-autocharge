import asyncio
import datetime as dt
from unittest.mock import AsyncMock, MagicMock, patch
import pytest
import bluelink
import config
import settings
import main
from main import (
    PlugInDetector,
    ensure_pending_sessions,
    handle_plugin_event,
    load_persisted_settings,
    run_loop,
    run_once,
)
from state import store


def _vstate(
    soc, *, range_miles=150, odometer_miles=10000, soh_percent=None, vehicle_id=None
):
    """Build a Bluelink VehicleState for patching bluelink.get_vehicle_state."""
    return bluelink.VehicleState(
        soc=soc, range_miles=range_miles, odometer_miles=odometer_miles,
        soh_percent=soh_percent, vehicle_id=vehicle_id,
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
    store.clear_trip_mode()
    store.notification_preferences = settings.NotificationPreferences()
    store.vehicle_profiles = {}
    store.pending_sessions = {}
    settings.clear_trip_mode()
    settings.save_session_active(False)
    for session_key in settings.load_pending_sessions():
        settings.clear_pending_session(session_key)
    yield
    store.clear_soc()
    store.clear_trip_mode()
    store.notification_preferences = settings.NotificationPreferences()
    store.vehicle_profiles = {}
    store.pending_sessions = {}
    settings.clear_trip_mode()
    settings.save_session_active(False)
    for session_key in settings.load_pending_sessions():
        settings.clear_pending_session(session_key)


async def test_returns_false_when_bluelink_fails():
    with patch("bluelink.get_vehicle_state", side_effect=RuntimeError("No vehicles found")):
        result = await handle_plugin_event(_mock_ohme_client())
    assert result is False
    assert store.automation_state == "error"
    assert store.automation_error_code == "bluelink_read_failed"


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
    await asyncio.sleep(0.35)


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


async def test_plug_in_notification_can_be_disabled(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    store.notification_preferences = settings.NotificationPreferences(plug_in=False)
    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock()), \
         patch("ntfy.send", new=AsyncMock()) as notify:
        assert await handle_plugin_event(_mock_ohme_client()) is True
    notify.assert_not_called()


async def test_plug_in_uses_profile_for_vehicle_returned_by_bluelink(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    store.set_vehicle_profiles({"car-2": settings.VehicleProfile(95, "05:45")})
    client = _mock_ohme_client()
    with patch(
        "bluelink.get_vehicle_state", return_value=_vstate(60, vehicle_id="car-2")
    ), patch("ohme_client.set_target", new=AsyncMock()) as set_target, patch(
        "ntfy.send", new=AsyncMock()
    ):
        assert await handle_plugin_event(client) is True
    set_target.assert_awaited_once_with(
        client, current_soc=60, target_percent=95, target_time=(5, 45)
    )


async def test_problem_notification_can_be_disabled():
    store.notification_preferences = settings.NotificationPreferences(problems=False)
    with patch("ntfy.send", new=AsyncMock()) as notify:
        await main._notify_plugin_failure("problem")
    notify.assert_not_called()


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
         patch("db.is_available", return_value=True), \
         patch("db.record_session", new=AsyncMock(return_value=7)) as mock_session, \
         patch("db.record_initial_session_event", new=AsyncMock(return_value=True)), \
         patch("db.record_initial_schedule", new=AsyncMock(return_value=True)) as mock_schedule:
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
         patch("db.is_available", return_value=True), \
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


async def test_disabled_persistence_does_not_create_session_outbox(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    with (
        patch("bluelink.get_vehicle_state", return_value=_vstate(90)),
        patch("db.is_enabled", return_value=False),
        patch("db.record_session", new=AsyncMock()) as record,
    ):
        assert await handle_plugin_event(
            _mock_ohme_client(), session_key="memory-only-session"
        ) is True

    record.assert_not_awaited()
    assert store.pending_sessions == {}
    assert settings.load_pending_sessions() == {}


async def test_session_row_recovers_after_database_outage(monkeypatch):
    """A successful target apply must survive Postgres being down at plug-in."""
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"
    client.next_slot_start = None
    client.next_slot_end = None
    plugged_at = dt.datetime(2026, 6, 1, 20, 0, tzinfo=dt.timezone.utc)

    with (
        patch(
            "bluelink.get_vehicle_state",
            return_value=_vstate(62, odometer_miles=12_345, soh_percent=98),
        ),
        patch("ohme_client.set_target", new=AsyncMock()),
        patch("ntfy.send", new=AsyncMock()),
        patch("db.is_enabled", return_value=True),
        patch("db.record_session", new=AsyncMock(side_effect=[None, 7])) as record,
        patch(
            "db.record_initial_session_event", new=AsyncMock(return_value=True)
        ) as event,
        patch("db.record_initial_schedule", new=AsyncMock(return_value=True)) as schedule,
    ):
        assert await handle_plugin_event(
            client, session_key="outage-session", plugged_in_at=plugged_at
        ) is True

        # Target configuration succeeds independently. Its history row remains
        # durably queued, and no audit write is attempted against a missing id.
        pending = settings.load_pending_sessions()
        assert pending["outage-session"]["socPercent"] == 62
        assert store.active_session_id is None
        event.assert_not_awaited()
        schedule.assert_not_awaited()

        assert await ensure_pending_sessions(
            active_session_key="outage-session"
        ) == 7

    assert record.await_count == 2
    assert store.active_session_id == 7
    assert store.active_session_key == "outage-session"
    assert settings.load_pending_sessions() == {}


async def test_session_outbox_recovers_after_process_state_is_lost(monkeypatch):
    """The JSON outbox, not process memory, is sufficient after a restart."""
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"

    with (
        patch("bluelink.get_vehicle_state", return_value=_vstate(90)),
        patch("db.is_enabled", return_value=True),
        patch("db.record_session", new=AsyncMock(side_effect=[None, 11])) as record,
        patch("db.record_initial_session_event", new=AsyncMock(return_value=True)),
    ):
        assert await handle_plugin_event(client, session_key="restart-session") is True
        assert "restart-session" in settings.load_pending_sessions()

        # Simulate a fresh AppState process while retaining settings.json.
        store.pending_sessions = {}
        store.active_session_id = None
        store.active_session_key = "restart-session"
        assert await ensure_pending_sessions(
            active_session_key="restart-session"
        ) == 11

    assert record.await_count == 2
    assert store.active_session_id == 11
    assert settings.load_pending_sessions() == {}


async def test_connected_poll_automatically_drains_session_outbox():
    from ohme import ChargerStatus

    payload = {
        "sessionKey": "poll-session",
        "vehicleName": "IONIQ 5",
        "socPercent": 55,
        "targetPercent": 80,
        "topupPercent": 25,
        "action": "configured",
        "pluggedInAt": "2026-06-01T20:00:00+00:00",
    }
    settings.save_pending_session(payload)
    detector = PlugInDetector()
    detector.was_connected = True
    detector.session_handled = True
    detector.session_key = "poll-session"
    client = _mock_ohme_client()
    client.energy = 1_500

    with patch("db.is_enabled", return_value=True), patch(
        "db.record_session", new=AsyncMock(return_value=23)
    ) as record:
        assert await detector.update(client, ChargerStatus.CHARGING) is True

    record.assert_awaited_once()
    assert store.active_session_id == 23
    assert store.active_session_key == "poll-session"
    assert settings.load_pending_sessions() == {}


async def test_full_acknowledged_payload_recreates_missing_database_row():
    payload = {
        "sessionKey": "restored-db-session",
        "rowPersisted": True,
        "vehicleName": "IONIQ 5",
        "socPercent": 55,
        "targetPercent": 80,
        "topupPercent": 25,
        "action": "configured",
        "pluggedInAt": "2026-06-01T20:00:00+00:00",
    }
    settings.save_pending_session(payload)

    with (
        patch("db.is_enabled", return_value=True),
        patch("db.get_session_id_by_key", new=AsyncMock(return_value=None)) as lookup,
        patch("db.record_session", new=AsyncMock(return_value=29)) as record,
    ):
        assert await ensure_pending_sessions(
            active_session_key="restored-db-session"
        ) == 29

    lookup.assert_awaited_once_with("restored-db-session")
    record.assert_awaited_once()
    assert settings.load_pending_sessions() == {}


async def test_database_outage_through_unplug_replays_final_close(monkeypatch):
    """Final energy survives clear_soc and close acknowledgement is retried."""
    from ohme import ChargerStatus

    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    client = _mock_ohme_client()
    client.current_vehicle = "IONIQ 5"
    client.energy = 18_500

    with (
        patch("bluelink.get_vehicle_state", return_value=_vstate(62)),
        patch("ohme_client.set_target", new=AsyncMock()),
        patch("ntfy.send", new=AsyncMock()),
        patch("db.is_enabled", return_value=True),
        patch("db.record_session", new=AsyncMock(side_effect=[None, None, 31])),
        patch("db.record_initial_session_event", new=AsyncMock(return_value=True)),
        patch("db.record_initial_schedule", new=AsyncMock(return_value=True)),
        patch("db.get_session_id_by_key", new=AsyncMock(return_value=31)),
        patch("db.close_session", new=AsyncMock(side_effect=[False, True])) as close,
    ):
        assert await handle_plugin_event(client, session_key="long-outage") is True
        detector = PlugInDetector()
        detector.was_connected = True
        detector.session_handled = True
        detector.session_key = "long-outage"
        store.record_session_energy(18_500)
        store.record_soc(80)

        # Postgres is still down at the physical boundary. clear_soc runs, but
        # the durable outbox retains the only final counter and SOC copy.
        client.energy = 0
        assert await detector.update(client, ChargerStatus.UNPLUGGED) is False
        staged = settings.load_pending_sessions()["long-outage"]
        assert staged["unplugged"] is True
        assert staged["finalEnergyWh"] == 18_500
        assert staged["endSocPercent"] == 80
        assert store.last_session_energy_wh is None

        # The row recovers first, but a failed close must not acknowledge the
        # item. A later disconnected poll/retry closes it and only then clears.
        await ensure_pending_sessions()
        assert "long-outage" in settings.load_pending_sessions()
        await ensure_pending_sessions()

    assert settings.load_pending_sessions() == {}
    assert close.await_count == 2
    close.assert_awaited_with(
        "long-outage",
        actual_energy_wh=18_500,
        end_soc_percent=80,
        completion_reason="unplugged",
    )


async def test_returns_false_when_ohme_fails_and_sends_only_failure_alert(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)

    with patch("bluelink.get_vehicle_state", return_value=_vstate(62)), \
         patch("ohme_client.set_target", new=AsyncMock(side_effect=Exception("Ohme API error"))), \
         patch("ntfy.send", new=AsyncMock()) as mock_notify:
        result = await handle_plugin_event(_mock_ohme_client())

    assert result is False
    assert store.automation_state == "error"
    assert store.automation_error_code == "ohme_target_failed"
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
    assert store.automation_state == "configured"


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


async def test_unplug_uses_last_session_energy_after_ohme_counter_resets():
    """Ohme resets ``client.energy`` to zero on the DISCONNECTED refresh."""
    from ohme import ChargerStatus

    reconcile = AsyncMock()
    detector = PlugInDetector(on_unplug=reconcile)
    detector.was_connected = True
    detector.session_handled = True
    detector.session_key = "session-1"
    store.active_session_id = 42
    store.record_session_energy(18_500)
    store.record_soc(80)
    client = _mock_ohme_client()
    client.energy = 0

    with patch("db.is_enabled", return_value=True), patch(
        "db.close_session", new=AsyncMock(return_value=True)
    ) as close:
        await detector.update(client, ChargerStatus.UNPLUGGED)

    close.assert_awaited_once_with(
        "session-1",
        actual_energy_wh=18_500.0,
        end_soc_percent=80,
        completion_reason="unplugged",
    )
    reconcile.assert_awaited_once_with("session-1", 42, 18_500)
    assert store.active_session_id is None


async def test_unplug_consumes_trip_mode():
    from ohme import ChargerStatus

    detector = PlugInDetector()
    detector.was_connected = True
    detector.session_handled = True
    detector.session_key = "trip-session"
    store.active_session_id = 42
    store.set_trip_mode(100, "06:30")
    settings.save_trip_mode(100, "06:30")
    client = _mock_ohme_client()
    client.energy = 1200

    with patch("db.is_enabled", return_value=True), \
         patch("db.close_session", new=AsyncMock(return_value=True)) as close, \
         patch("db.record_session_event", new=AsyncMock()) as event:
        connected = await detector.update(client, ChargerStatus.UNPLUGGED)

    assert connected is False
    assert store.trip_mode_enabled is False
    assert settings.load_trip_mode() is None
    close.assert_awaited_once()
    event.assert_awaited_once_with(
        42, "trip_mode_consumed", {"target": 100, "readyBy": "06:30"}
    )


def test_pending_trip_mode_is_restored_after_restart():
    settings.save_trip_mode(95, "05:30")
    store.clear_trip_mode()

    load_persisted_settings()

    assert store.trip_target == 95
    assert store.trip_ready_by == "05:30"


# --- persisted session marker ---


def test_session_active_round_trip():
    """save/load round-trips, and an unset marker reads as False (not handled)."""
    settings.save_session_active(False)
    assert settings.load_session_active() is False
    assert settings.save_session_active(True) is True
    assert settings.load_session_active() is True
    settings.save_session_active(False)
    assert settings.load_session_active() is False
