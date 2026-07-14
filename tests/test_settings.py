"""Tests for the JSON-file-backed runtime settings.

Each test points ``settings.SETTINGS_PATH`` at a fresh ``tmp_path`` file so the
read-modify-write helpers operate on a throwaway file with no cross-test bleed.
"""

import glob
import json

import pytest

import settings


@pytest.fixture
def settings_path(tmp_path, monkeypatch):
    path = tmp_path / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(path))
    return path


def _write_raw(path, data) -> None:
    """Write an arbitrary JSON payload directly, bypassing the setters."""
    path.write_text(json.dumps(data), encoding="utf-8")


# --- parse_hhmm ------------------------------------------------------------

@pytest.mark.parametrize(
    "value,expected",
    [
        ("00:00", (0, 0)),
        ("07:30", (7, 30)),
        ("23:59", (23, 59)),
        ("7:30", None),     # hour must be zero-padded
        ("24:00", None),    # hour out of range
        ("12:60", None),    # minute out of range
        ("0630", None),     # missing colon
        ("nonsense", None),
        ("", None),
        (None, None),
        (730, None),        # not a string
    ],
)
def test_parse_hhmm(value, expected):
    assert settings.parse_hhmm(value) == expected


# --- charge target ---------------------------------------------------------

def test_target_round_trip(settings_path):
    assert settings.save_target(75) is True
    assert settings.load_target() == 75


def test_load_target_none_when_unset(settings_path):
    assert settings.load_target() is None


def test_load_target_rejects_out_of_range(settings_path):
    # save coerces to int but load enforces the TARGET_MIN..TARGET_MAX bounds.
    settings.save_target(5)     # below TARGET_MIN (10)
    assert settings.load_target() is None
    settings.save_target(150)   # above TARGET_MAX (100)
    assert settings.load_target() is None


def test_load_target_none_on_non_numeric(settings_path):
    _write_raw(settings_path, {"chargeTarget": "abc"})
    assert settings.load_target() is None


# --- ready-by --------------------------------------------------------------

def test_ready_by_set_and_clear(settings_path):
    settings.save_ready_by("07:15")
    assert settings.load_ready_by() == "07:15"
    settings.save_ready_by(None)
    assert settings.load_ready_by() is None


def test_load_ready_by_ignores_invalid_persisted_value(settings_path):
    _write_raw(settings_path, {"readyBy": "99:99"})
    assert settings.load_ready_by() is None


# --- per-weekday targets ---------------------------------------------------

def test_day_targets_round_trip(settings_path):
    settings.save_day_targets({0: 90, 6: 70})
    assert settings.load_day_targets() == {0: 90, 6: 70}


def test_day_targets_filters_malformed_and_out_of_range(settings_path):
    _write_raw(
        settings_path,
        {"dayTargets": {"0": 90, "7": 50, "2": 5, "x": 80, "3": "bad"}},
    )
    # day 7 is out of 0..6; day 2's 5% is below TARGET_MIN; "x" and "bad" don't
    # parse as ints — only the valid {0: 90} survives.
    assert settings.load_day_targets() == {0: 90}


def test_save_empty_day_targets_clears_key(settings_path):
    settings.save_day_targets({0: 90})
    settings.save_day_targets({})
    assert settings.load_day_targets() == {}
    assert "dayTargets" not in json.loads(settings_path.read_text())


# --- one-session trip mode -------------------------------------------------

def test_trip_mode_round_trip_and_clear(settings_path):
    assert settings.load_trip_mode() is None
    assert settings.save_trip_mode(100, "06:30") is True
    assert settings.load_trip_mode() == (100, "06:30")
    assert settings.clear_trip_mode() is True
    assert settings.load_trip_mode() is None


@pytest.mark.parametrize(
    "raw",
    [
        {"targetPercent": 5, "readyBy": "06:30"},
        {"targetPercent": 100, "readyBy": "25:00"},
        {"targetPercent": "bad", "readyBy": None},
    ],
)
def test_load_trip_mode_rejects_invalid_values(settings_path, raw):
    _write_raw(settings_path, {"tripMode": raw})
    assert settings.load_trip_mode() is None


# --- notification preferences --------------------------------------------

def test_notification_preferences_round_trip(settings_path):
    preferences = settings.NotificationPreferences(
        plug_in=False,
        failure_polls=3,
        minimum_charge_kwh=2.5,
        aux_battery_below_percent=35,
    )
    assert settings.save_notification_preferences(preferences) is True
    assert settings.load_notification_preferences() == preferences


def test_notification_preferences_validate_each_persisted_field(settings_path):
    _write_raw(settings_path, {"notificationPreferences": {
        "plugIn": "yes",
        "chargeComplete": False,
        "failurePolls": 99,
        "minimumChargeKwh": -1,
        "auxBatteryBelowPercent": 0,
    }})
    loaded = settings.load_notification_preferences()
    assert loaded.plug_in is True
    assert loaded.charge_complete is False
    assert loaded.failure_polls == 5
    assert loaded.minimum_charge_kwh == 0.1
    assert loaded.aux_battery_below_percent is None


# --- vehicle id ------------------------------------------------------------

def test_vehicle_id_set_and_clear(settings_path):
    settings.save_vehicle_id("vin-123")
    assert settings.load_vehicle_id() == "vin-123"
    settings.save_vehicle_id(None)
    assert settings.load_vehicle_id() is None


def test_load_vehicle_id_none_for_empty_or_non_string(settings_path):
    _write_raw(settings_path, {"vehicleId": ""})
    assert settings.load_vehicle_id() is None
    _write_raw(settings_path, {"vehicleId": 123})
    assert settings.load_vehicle_id() is None


def test_vehicle_profiles_round_trip_and_clear(settings_path):
    profiles = {
        "car-1": settings.VehicleProfile(80, "07:30"),
        "car-2": settings.VehicleProfile(100, None),
    }
    assert settings.save_vehicle_profiles(profiles) is True
    assert settings.load_vehicle_profiles() == profiles
    assert settings.save_vehicle_profiles({}) is True
    assert settings.load_vehicle_profiles() == {}


def test_vehicle_profiles_skip_invalid_entries(settings_path):
    _write_raw(settings_path, {"vehicleProfiles": {
        "good": {"targetPercent": 90, "readyBy": "06:15"},
        "low": {"targetPercent": 5, "readyBy": None},
        "bad-time": {"targetPercent": 80, "readyBy": "25:00"},
        "bad-shape": "profile",
    }})
    assert settings.load_vehicle_profiles() == {
        "good": settings.VehicleProfile(90, "06:15")
    }


# --- session-active marker -------------------------------------------------

def test_session_active_round_trip(settings_path):
    assert settings.load_session_active() is False  # default when unset
    settings.save_session_active(True)
    assert settings.load_session_active() is True
    settings.save_session_active(False)
    assert settings.load_session_active() is False


def test_session_marker_round_trip_and_clear(settings_path):
    assert settings.load_session_key() is None
    assert settings.save_session_marker("session-123", handled=False) is True
    assert settings.load_session_key() == "session-123"
    assert settings.load_session_active() is False
    settings.save_session_marker("session-123", handled=True)
    assert settings.load_session_active() is True
    assert settings.clear_session_marker() is True
    assert settings.load_session_key() is None
    assert settings.load_session_active() is False


def test_pending_sessions_round_trip_and_acknowledge_individually(settings_path):
    first = {"sessionKey": "session-1", "socPercent": 62, "action": "configured"}
    second = {
        "sessionKey": "session-2",
        "socPercent": 80,
        "action": "skipped_at_target",
    }

    assert settings.save_pending_session(first) is True
    assert settings.save_pending_session(second) is True
    assert settings.load_pending_sessions() == {
        "session-1": first,
        "session-2": second,
    }

    assert settings.clear_pending_session("session-1") is True
    assert settings.load_pending_sessions() == {"session-2": second}
    assert settings.clear_pending_session("session-2") is True
    assert settings.load_pending_sessions() == {}


def test_pending_sessions_ignore_invalid_entries(settings_path):
    _write_raw(
        settings_path,
        {
            "pendingSessions": {
                "good": {"sessionKey": "good", "action": "configured"},
                "wrong-key": {"sessionKey": "other"},
                "bad-shape": "not-an-object",
            }
        },
    )
    assert settings.load_pending_sessions() == {
        "good": {"sessionKey": "good", "action": "configured"}
    }


# --- preservation & robustness ---------------------------------------------

def test_setters_preserve_other_keys(settings_path):
    settings.save_target(70)
    settings.save_ready_by("06:30")
    settings.save_day_targets({0: 90})
    settings.save_vehicle_id("v1")
    settings.save_vehicle_profiles({"v1": settings.VehicleProfile(85, None)})
    settings.save_trip_mode(95, None)
    settings.save_notification_preferences(
        settings.NotificationPreferences(weekly_digest=False)
    )
    settings.save_session_active(True)
    assert settings.load_target() == 70
    assert settings.load_ready_by() == "06:30"
    assert settings.load_day_targets() == {0: 90}
    assert settings.load_vehicle_id() == "v1"
    assert settings.load_vehicle_profiles() == {
        "v1": settings.VehicleProfile(85, None)
    }
    assert settings.load_trip_mode() == (95, None)
    assert settings.load_notification_preferences().weekly_digest is False
    assert settings.load_session_active() is True


def test_load_tolerates_corrupt_json(settings_path):
    settings_path.write_text("{not valid json", encoding="utf-8")
    assert settings.load_target() is None
    assert settings.load_day_targets() == {}
    assert settings.load_session_active() is False


def test_load_tolerates_non_dict_top_level(settings_path):
    _write_raw(settings_path, [1, 2, 3])
    assert settings.load_target() is None
    assert settings.load_day_targets() == {}


def test_missing_file_returns_defaults(settings_path):
    # settings_path doesn't exist yet.
    assert settings.load_target() is None
    assert settings.load_ready_by() is None
    assert settings.load_day_targets() == {}
    assert settings.load_vehicle_id() is None
    assert settings.load_session_active() is False


def test_save_creates_missing_directory(tmp_path, monkeypatch):
    nested = tmp_path / "sub" / "dir" / "settings.json"
    monkeypatch.setattr(settings, "SETTINGS_PATH", str(nested))
    assert settings.save_target(70) is True
    assert settings.load_target() == 70


def test_atomic_save_leaves_no_temp_files(settings_path, tmp_path):
    settings.save_target(70)
    # _save writes to a ".settings-*.tmp" then os.replace()s it into place.
    assert glob.glob(str(tmp_path / ".settings-*")) == []
