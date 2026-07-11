"""Tests for the in-memory AppState store and StatusSnapshot.

These exercise target resolution (the base/override/per-weekday logic the whole
app reads via ``effective_target``), vehicle selection precedence, ready-by
parsing, and the poll failure tracking that paces the loop and the alerts. Each
test builds its own ``AppState`` so the module-level ``store`` singleton (and
other suites) are untouched.

Per the repo's timezone rule, ``_today_weekday`` is patched to a fixed day rather
than asserting against the real clock.
"""

import json
from types import SimpleNamespace
from unittest.mock import patch

import config
from state import AppState, StatusSnapshot


# --- charge target / effective target --------------------------------------

def test_charge_target_uses_env_default_when_no_override(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    assert AppState().charge_target == 80


def test_charge_target_override_wins(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    s = AppState()
    s.set_charge_target(65)
    assert s.charge_target == 65


def test_effective_target_base_when_no_day_overrides(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    s = AppState()
    with patch("state._today_weekday", return_value=2):
        assert s.effective_target == 80


def test_effective_target_uses_todays_override(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    s = AppState()
    s.set_day_targets({2: 95})
    with patch("state._today_weekday", return_value=2):
        assert s.effective_target == 95
    with patch("state._today_weekday", return_value=3):
        assert s.effective_target == 80  # a different day falls back to base


def test_effective_target_combines_base_override_and_day_targets(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    s = AppState()
    s.set_charge_target(70)  # runtime base override
    with patch("state._today_weekday", return_value=1):
        assert s.effective_target == 70  # no day override -> base override
        s.set_day_targets({1: 90})
        assert s.effective_target == 90  # today's override wins over base


def test_trip_mode_takes_precedence_then_restores_normal_target(monkeypatch):
    monkeypatch.setattr(config, "CHARGE_TARGET", 80)
    s = AppState()
    s.set_day_targets({2: 90})
    with patch("state._today_weekday", return_value=2):
        s.set_trip_mode(100, "05:45")
        assert s.effective_target == 100
        assert s.effective_ready_by == "05:45"
        assert s.ready_by_tuple == (5, 45)
        assert s.trip_mode_enabled is True
        s.clear_trip_mode()
        assert s.effective_target == 90
        assert s.trip_mode_enabled is False


def test_trip_mode_without_departure_ignores_permanent_ready_by():
    s = AppState()
    s.set_ready_by("07:30")
    s.set_trip_mode(100, None)
    assert s.effective_ready_by is None
    assert s.ready_by_tuple is None


# --- vehicle selection precedence ------------------------------------------

def test_selected_vehicle_id_precedence(monkeypatch):
    monkeypatch.setattr(config, "HYUNDAI_VEHICLE_ID", "env-vin")
    s = AppState()
    assert s.selected_vehicle_id == "env-vin"   # env default
    s.set_vehicle_id("runtime-vin")
    assert s.selected_vehicle_id == "runtime-vin"  # runtime override wins


def test_selected_vehicle_id_none_when_unset(monkeypatch):
    monkeypatch.setattr(config, "HYUNDAI_VEHICLE_ID", "")
    assert AppState().selected_vehicle_id is None


# --- ready-by parsing ------------------------------------------------------

def test_ready_by_tuple_parses_valid():
    s = AppState()
    s.set_ready_by("07:30")
    assert s.ready_by_tuple == (7, 30)


def test_ready_by_tuple_none_when_unset_or_invalid():
    s = AppState()
    assert s.ready_by_tuple is None
    s.set_ready_by("nonsense")
    assert s.ready_by_tuple is None


# --- poll failure tracking & snapshot update -------------------------------

def test_record_poll_failure_increments_and_keeps_last_good_snapshot():
    s = AppState()
    good = StatusSnapshot(battery_percent=62)
    s.update(good)
    assert s.ready is True and s.consecutive_poll_failures == 0

    s.record_poll_failure("poll_failed")
    s.record_poll_failure("poll_failed")
    assert s.consecutive_poll_failures == 2
    assert s.last_poll_error == "poll_failed"
    assert s.status is good  # the good snapshot is retained through failures


def test_update_with_clean_snapshot_resets_failures():
    s = AppState()
    s.record_poll_failure("poll_failed")
    s.update(StatusSnapshot(battery_percent=70))
    assert s.consecutive_poll_failures == 0
    assert s.last_poll_error is None
    assert s.ready is True


def test_update_with_error_snapshot_does_not_reset_failures():
    s = AppState()
    s.record_poll_failure("poll_failed")
    s.update(StatusSnapshot(error="boom"))
    assert s.consecutive_poll_failures == 1  # error snapshot must not clear it
    assert s.status.error == "boom"


# --- cached vehicle readings -----------------------------------------------

def test_record_soc_sets_value_and_timestamp():
    s = AppState()
    s.record_soc(55)
    assert s.last_soc == 55
    assert s.last_soc_at is not None


def test_record_and_clear_vehicle_state():
    s = AppState()
    vstate = SimpleNamespace(
        soc=62, range_miles=180, odometer_miles=12000, soh_percent=98,
        is_locked=True, latitude=51.5, longitude=-0.1,
        aux_battery_percent=85, tyre_pressure_warning=True,
        washer_fluid_warning=False, key_battery_warning=None, open_items=["Boot"],
    )
    s.record_vehicle_state(vstate)
    assert s.last_soc == 62
    assert s.last_range_miles == 180
    assert s.last_odometer_miles == 12000
    assert s.last_soh_percent == 98
    assert s.last_is_locked is True
    assert s.last_aux_battery_percent == 85
    assert s.last_tyre_pressure_warning is True
    assert s.last_open_items == ["Boot"]
    assert s.last_soc_at is not None

    s.plugin_failure_notified = True
    s.clear_soc()
    assert s.last_soc is None
    assert s.last_range_miles is None
    assert s.last_soh_percent is None
    assert s.last_aux_battery_percent is None
    assert s.last_tyre_pressure_warning is None
    assert s.last_open_items == []
    assert s.last_soc_at is None
    assert s.plugin_failure_notified is False  # cleared for the next session


# --- snapshot serialisation ------------------------------------------------

def test_status_snapshot_to_dict_is_json_serialisable():
    snap = StatusSnapshot(battery_percent=62, slots=[{"start": "00:00"}])
    d = snap.to_dict()
    assert d["battery_percent"] == 62
    assert d["slots"] == [{"start": "00:00"}]
    json.dumps(d)  # must not raise
