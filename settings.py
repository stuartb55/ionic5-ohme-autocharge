"""Runtime-adjustable settings, persisted to a small JSON file.

Holds the dashboard-adjustable settings — the charge target and an optional
"ready-by" departure time — written to ``SETTINGS_PATH`` so they survive
container restarts. If the file can't be read or written the app degrades
gracefully: settings fall back to env defaults / off and live in memory for the
process lifetime.

All keys live in one JSON object, so each setter does a read-modify-write to
avoid clobbering the others.
"""

from __future__ import annotations

import json
import logging
import os
import re
import tempfile
from dataclasses import dataclass

logger = logging.getLogger(__name__)

# Sensible bounds for a charge target. Below ~10% there's no point scheduling;
# 100% is the hard ceiling.
TARGET_MIN = 10
TARGET_MAX = 100

# Where the persisted settings live. The Docker image creates /app/data (owned by
# the runtime user) and the compose files mount a volume there.
SETTINGS_PATH = os.getenv("SETTINGS_PATH", "/app/data/settings.json")

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


@dataclass(frozen=True)
class NotificationPreferences:
    """User-adjustable ntfy categories and evidence-based thresholds."""

    plug_in: bool = True
    charge_complete: bool = True
    problems: bool = True
    vehicle_health: bool = True
    weekly_digest: bool = True
    failure_polls: int = 5
    minimum_charge_kwh: float = 0.1
    aux_battery_below_percent: int | None = None

    def to_json(self) -> dict:
        return {
            "plugIn": self.plug_in,
            "chargeComplete": self.charge_complete,
            "problems": self.problems,
            "vehicleHealth": self.vehicle_health,
            "weeklyDigest": self.weekly_digest,
            "failurePolls": self.failure_polls,
            "minimumChargeKwh": self.minimum_charge_kwh,
            "auxBatteryBelowPercent": self.aux_battery_below_percent,
        }


@dataclass(frozen=True)
class VehicleProfile:
    """Charging defaults bound to one stable Hyundai vehicle id."""

    target_percent: int
    ready_by: str | None = None

    def to_json(self) -> dict:
        return {"targetPercent": self.target_percent, "readyBy": self.ready_by}


def parse_hhmm(value: object) -> tuple[int, int] | None:
    """Parse a 24h ``HH:MM`` string into an (hour, minute) tuple, or None."""
    if not isinstance(value, str):
        return None
    m = _HHMM_RE.match(value)
    if not m:
        return None
    return int(m.group(1)), int(m.group(2))


def _load() -> dict:
    """Read the settings object from disk, or {} when absent/unreadable."""
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        return data if isinstance(data, dict) else {}
    except FileNotFoundError:
        return {}
    except (OSError, ValueError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable settings file at %s", SETTINGS_PATH, exc_info=True)
        return {}


def _save(data: dict) -> bool:
    """Persist the settings object atomically. Best-effort: False (and logs) on failure."""
    try:
        directory = os.path.dirname(SETTINGS_PATH) or "."
        os.makedirs(directory, exist_ok=True)
        # Write atomically so a crash mid-write can't leave a truncated file.
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump(data, fh)
            os.replace(tmp, SETTINGS_PATH)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        logger.warning("Could not persist settings to %s — keeping in memory only", SETTINGS_PATH, exc_info=True)
        return False


def load_target() -> int | None:
    """Return the persisted charge target, or None if unavailable/invalid."""
    data = _load()
    try:
        value = int(data["chargeTarget"])
    except (KeyError, ValueError, TypeError):
        return None
    if not TARGET_MIN <= value <= TARGET_MAX:
        logger.warning("Persisted charge target %s out of range — ignoring", value)
        return None
    return value


def save_target(value: int) -> bool:
    """Persist the charge target, preserving other settings. Best-effort."""
    data = _load()
    data["chargeTarget"] = int(value)
    return _save(data)


def load_ready_by() -> str | None:
    """Return the persisted ready-by time as ``HH:MM``, or None if unset/invalid."""
    value = _load().get("readyBy")
    if value is None:
        return None
    if parse_hhmm(value) is None:
        logger.warning("Persisted readyBy %r invalid — ignoring", value)
        return None
    return value


def save_ready_by(value: str | None) -> bool:
    """Persist (or clear, when None) the ready-by time, preserving other settings."""
    data = _load()
    if value is None:
        data.pop("readyBy", None)
    else:
        data["readyBy"] = value
    return _save(data)


def load_day_targets() -> dict[int, int]:
    """Return per-weekday target overrides as {0(Mon)..6(Sun): percent}.

    Skips any malformed or out-of-range entries. Empty dict when none are set.
    """
    raw = _load().get("dayTargets")
    if not isinstance(raw, dict):
        return {}
    result: dict[int, int] = {}
    for key, value in raw.items():
        try:
            day, pct = int(key), int(value)
        except (ValueError, TypeError):
            continue
        if 0 <= day <= 6 and TARGET_MIN <= pct <= TARGET_MAX:
            result[day] = pct
    return result


def save_day_targets(day_targets: dict[int, int]) -> bool:
    """Persist (or clear, when empty) the per-weekday overrides, preserving other settings."""
    data = _load()
    if day_targets:
        data["dayTargets"] = {str(day): int(pct) for day, pct in day_targets.items()}
    else:
        data.pop("dayTargets", None)
    return _save(data)


def load_trip_mode() -> tuple[int, str | None] | None:
    """Return the pending one-session trip override, or None when inactive."""
    raw = _load().get("tripMode")
    if not isinstance(raw, dict):
        return None
    try:
        target = int(raw["targetPercent"])
    except (KeyError, ValueError, TypeError):
        return None
    ready_by = raw.get("readyBy")
    if not TARGET_MIN <= target <= TARGET_MAX:
        logger.warning("Persisted trip target %s out of range — ignoring", target)
        return None
    if ready_by is not None and parse_hhmm(ready_by) is None:
        logger.warning("Persisted trip readyBy %r invalid — ignoring", ready_by)
        return None
    return target, ready_by


def save_trip_mode(target_percent: int, ready_by: str | None) -> bool:
    """Persist a one-session trip override, preserving permanent settings."""
    data = _load()
    data["tripMode"] = {"targetPercent": int(target_percent), "readyBy": ready_by}
    return _save(data)


def clear_trip_mode() -> bool:
    """Consume or cancel the pending trip override."""
    data = _load()
    data.pop("tripMode", None)
    return _save(data)


def load_notification_preferences() -> NotificationPreferences:
    """Load validated notification controls, defaulting each malformed field."""
    raw = _load().get("notificationPreferences")
    if not isinstance(raw, dict):
        return NotificationPreferences()
    defaults = NotificationPreferences()

    def boolean(key: str, default: bool) -> bool:
        value = raw.get(key)
        return value if isinstance(value, bool) else default

    def integer(key: str, default: int, low: int, high: int) -> int:
        value = raw.get(key)
        return (
            value
            if isinstance(value, int) and not isinstance(value, bool) and low <= value <= high
            else default
        )

    minimum = raw.get("minimumChargeKwh")
    if not isinstance(minimum, (int, float)) or isinstance(minimum, bool) or not 0 <= minimum <= 100:
        minimum = defaults.minimum_charge_kwh
    aux = raw.get("auxBatteryBelowPercent")
    if aux is not None and (not isinstance(aux, int) or isinstance(aux, bool) or not 1 <= aux <= 100):
        aux = None
    return NotificationPreferences(
        plug_in=boolean("plugIn", defaults.plug_in),
        charge_complete=boolean("chargeComplete", defaults.charge_complete),
        problems=boolean("problems", defaults.problems),
        vehicle_health=boolean("vehicleHealth", defaults.vehicle_health),
        weekly_digest=boolean("weeklyDigest", defaults.weekly_digest),
        failure_polls=integer("failurePolls", defaults.failure_polls, 1, 20),
        minimum_charge_kwh=float(minimum),
        aux_battery_below_percent=aux,
    )


def save_notification_preferences(value: NotificationPreferences) -> bool:
    """Persist the complete notification preference set."""
    data = _load()
    data["notificationPreferences"] = value.to_json()
    return _save(data)


def load_vehicle_id() -> str | None:
    """Return the persisted selected Hyundai vehicle id, or None if unset/invalid."""
    value = _load().get("vehicleId")
    return value if isinstance(value, str) and value else None


def save_vehicle_id(value: str | None) -> bool:
    """Persist (or clear, when None) the selected vehicle id, preserving other settings."""
    data = _load()
    if value:
        data["vehicleId"] = value
    else:
        data.pop("vehicleId", None)
    return _save(data)


def load_vehicle_profiles() -> dict[str, VehicleProfile]:
    """Return every valid per-vehicle profile; skip malformed entries."""
    raw = _load().get("vehicleProfiles")
    if not isinstance(raw, dict):
        return {}
    profiles: dict[str, VehicleProfile] = {}
    for vehicle_id, value in raw.items():
        if not isinstance(vehicle_id, str) or not vehicle_id or not isinstance(value, dict):
            continue
        try:
            target = int(value["targetPercent"])
        except (KeyError, TypeError, ValueError):
            continue
        ready_by = value.get("readyBy")
        if not TARGET_MIN <= target <= TARGET_MAX:
            continue
        if ready_by is not None and parse_hhmm(ready_by) is None:
            continue
        profiles[vehicle_id] = VehicleProfile(target, ready_by)
    return profiles


def save_vehicle_profiles(profiles: dict[str, VehicleProfile]) -> bool:
    """Persist the complete vehicle-profile mapping."""
    data = _load()
    if profiles:
        data["vehicleProfiles"] = {
            vehicle_id: profile.to_json() for vehicle_id, profile in profiles.items()
        }
    else:
        data.pop("vehicleProfiles", None)
    return _save(data)


def load_session_active() -> bool:
    """Return whether the currently-connected plug-in session was already handled.

    Persisted across restarts so :meth:`main.PlugInDetector.prime` can tell a
    restart mid-handled-session (don't re-record/re-notify) from a car that was
    plugged in while we were down (must still be configured). Defaults to False
    when unset or unreadable.
    """
    return _load().get("sessionActive") is True


def save_session_active(value: bool) -> bool:
    """Persist whether the active plug-in session has been handled. Best-effort."""
    data = _load()
    data["sessionActive"] = bool(value)
    if not value:
        # Legacy callers use False to mean the physical session ended.
        data.pop("sessionKey", None)
    return _save(data)


def load_session_key() -> str | None:
    """Stable idempotency key for the physically connected session, if any."""
    value = _load().get("sessionKey")
    return value if isinstance(value, str) and value else None


def save_session_marker(session_key: str, *, handled: bool) -> bool:
    """Atomically persist the active session key and whether it was handled."""
    data = _load()
    data["sessionKey"] = session_key
    data["sessionActive"] = handled
    return _save(data)


def clear_session_marker() -> bool:
    """Clear all state for the session that has just been unplugged."""
    data = _load()
    data.pop("sessionKey", None)
    data["sessionActive"] = False
    return _save(data)
