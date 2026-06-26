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

logger = logging.getLogger(__name__)

# Sensible bounds for a charge target. Below ~10% there's no point scheduling;
# 100% is the hard ceiling.
TARGET_MIN = 10
TARGET_MAX = 100

# Where the persisted settings live. The Docker image creates /app/data (owned by
# the runtime user) and the compose files mount a volume there.
SETTINGS_PATH = os.getenv("SETTINGS_PATH", "/app/data/settings.json")

_HHMM_RE = re.compile(r"^([01]\d|2[0-3]):([0-5]\d)$")


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
