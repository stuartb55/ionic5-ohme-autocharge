"""Runtime-adjustable settings, persisted to a small JSON file.

Currently this holds just the charge target, which the dashboard can change at
runtime (see ``PUT /api/settings/target``). The value is written to
``SETTINGS_PATH`` so it survives container restarts; if that file can't be read
or written the app degrades gracefully — the target simply falls back to the
``CHARGE_TARGET`` env default and lives in memory for the process lifetime.
"""

from __future__ import annotations

import json
import logging
import os
import tempfile

logger = logging.getLogger(__name__)

# Sensible bounds for a charge target. Below ~10% there's no point scheduling;
# 100% is the hard ceiling.
TARGET_MIN = 10
TARGET_MAX = 100

# Where the persisted settings live. The Docker image creates /app/data (owned by
# the runtime user) and the compose files mount a volume there.
SETTINGS_PATH = os.getenv("SETTINGS_PATH", "/app/data/settings.json")


def load_target() -> int | None:
    """Return the persisted charge target, or None if unavailable/invalid."""
    try:
        with open(SETTINGS_PATH, encoding="utf-8") as fh:
            data = json.load(fh)
        value = int(data["chargeTarget"])
    except FileNotFoundError:
        return None
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        logger.warning("Ignoring unreadable settings file at %s", SETTINGS_PATH, exc_info=True)
        return None
    if not TARGET_MIN <= value <= TARGET_MAX:
        logger.warning("Persisted charge target %s out of range — ignoring", value)
        return None
    return value


def save_target(value: int) -> bool:
    """Persist the charge target. Best-effort: returns False (and logs) on failure."""
    try:
        os.makedirs(os.path.dirname(SETTINGS_PATH) or ".", exist_ok=True)
        # Write atomically so a crash mid-write can't leave a truncated file.
        directory = os.path.dirname(SETTINGS_PATH) or "."
        fd, tmp = tempfile.mkstemp(dir=directory, prefix=".settings-", suffix=".tmp")
        try:
            with os.fdopen(fd, "w", encoding="utf-8") as fh:
                json.dump({"chargeTarget": int(value)}, fh)
            os.replace(tmp, SETTINGS_PATH)
        finally:
            if os.path.exists(tmp):
                os.unlink(tmp)
        return True
    except OSError:
        logger.warning("Could not persist settings to %s — keeping in memory only", SETTINGS_PATH, exc_info=True)
        return False
