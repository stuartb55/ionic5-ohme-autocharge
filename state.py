"""In-memory state shared between the polling loop and the HTTP API.

The poll loop writes a fresh :class:`StatusSnapshot` on every iteration; the API
read endpoints serve that cached snapshot so a browser request never blocks on a
live call to Ohme. Live calls (the charge summary) go through ``client_lock`` so
they never race the loop's own use of the single authenticated Ohme client.
"""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field, asdict
from typing import Any, Optional

import config


@dataclass
class StatusSnapshot:
    """Latest known vehicle + charger state. All fields JSON-serialisable."""

    # Vehicle
    vehicle_name: Optional[str] = None
    battery_percent: Optional[int] = None

    # Charger
    charger_status: str = "unknown"  # ChargerStatus value, e.g. "charging"
    connected: bool = False
    charger_online: bool = False
    # True while Ohme is in MAX_CHARGE mode (the dashboard's "boost" toggle).
    max_charge: bool = False
    charger_model: Optional[str] = None
    power_watts: float = 0.0
    power_amps: float = 0.0
    power_volts: Optional[int] = None
    target_percent: Optional[int] = None
    session_energy_wh: float = 0.0

    # Schedule
    slots: list[dict[str, Any]] = field(default_factory=list)
    next_slot_start: Optional[str] = None
    next_slot_end: Optional[str] = None
    # End of the last scheduled slot — when the charge is projected to finish.
    # None when disconnected or no schedule is allocated yet.
    projected_finish: Optional[str] = None

    # Meta
    updated_at: Optional[str] = None
    error: Optional[str] = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


class AppState:
    """Process-wide singleton holding the latest snapshot and the Ohme client."""

    def __init__(self) -> None:
        self.status = StatusSnapshot()
        self.client: Any = None
        self.client_lock = asyncio.Lock()
        self.ready = False  # True once the first successful poll has populated state
        # Real vehicle SOC captured from Bluelink at the last plug-in event. The
        # Ohme client's own `battery` reading is unreliable, so the snapshot
        # prefers this value when available.
        self.last_soc: Optional[int] = None
        # Runtime charge-target override set from the dashboard. None means "use
        # the CHARGE_TARGET env default"; see the `charge_target` property.
        self.charge_target_override: Optional[int] = None
        # Why the most recent poll failed ("poll_failed", "login_failed"), or
        # None when it succeeded. Failures keep the previous snapshot so the
        # dashboard shows last-known-good data rather than going blank.
        self.last_poll_error: Optional[str] = None
        # How many polls in a row have failed. Drives the "can't reach Ohme"
        # alert (sent once when a threshold is crossed) and its recovery notice.
        self.consecutive_poll_failures: int = 0
        # True once the user has been alerted that handling the current plug-in
        # is failing, so the per-poll retries don't re-notify. Cleared when a
        # plug-in is handled successfully and when the car unplugs.
        self.plugin_failure_notified: bool = False

    @property
    def charge_target(self) -> int:
        """The active charge target: the runtime override if set, else the env default."""
        return self.charge_target_override if self.charge_target_override is not None else config.CHARGE_TARGET

    def set_charge_target(self, value: int) -> None:
        """Set the runtime charge-target override (does not persist; see settings.save_target)."""
        self.charge_target_override = int(value)

    def update(self, snapshot: StatusSnapshot) -> None:
        self.status = snapshot
        if snapshot.error is None:
            self.ready = True
            self.last_poll_error = None
            self.consecutive_poll_failures = 0

    def record_poll_failure(self, reason: str) -> None:
        """Note a failed poll without discarding the last good snapshot."""
        self.last_poll_error = reason
        self.consecutive_poll_failures += 1

    def record_soc(self, soc: int) -> None:
        """Remember the real vehicle SOC fetched from Bluelink at plug-in."""
        self.last_soc = soc

    def clear_soc(self) -> None:
        """Forget the plug-in SOC — it is stale the moment the car unplugs."""
        self.last_soc = None
        # New session, clean slate for the plug-in failure alert.
        self.plugin_failure_notified = False


# Module-level singleton imported by api.py and tests.
store = AppState()
