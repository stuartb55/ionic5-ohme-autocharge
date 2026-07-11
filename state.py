"""In-memory state shared between the polling loop and the HTTP API.

The poll loop writes a fresh :class:`StatusSnapshot` on every iteration; the API
read endpoints serve that cached snapshot so a browser request never blocks on a
live call to Ohme. Live calls (the charge summary) go through ``client_lock`` so
they never race the loop's own use of the single authenticated Ohme client.
"""

from __future__ import annotations

import asyncio
import datetime
import time
from dataclasses import dataclass, field, asdict
from typing import Any, Optional
from zoneinfo import ZoneInfo

import config
from settings import NotificationPreferences


def _today_weekday() -> int:
    """Weekday (Mon=0 … Sun=6) for "now" in the configured timezone.

    Plug-in time decides which day's target applies, and Ohme's day boundaries
    are local, so use config.TIMEZONE rather than the host (UTC in containers).
    """
    try:
        return datetime.datetime.now(ZoneInfo(config.TIMEZONE)).weekday()
    except Exception:  # noqa: BLE001 - bad TIMEZONE; fall back to host-local
        return datetime.datetime.now().weekday()


@dataclass
class StatusSnapshot:
    """Latest known vehicle + charger state. All fields JSON-serialisable."""

    # Vehicle
    vehicle_name: Optional[str] = None
    battery_percent: Optional[int] = None
    # Estimated driving range (miles) from Bluelink at the last plug-in. None
    # when the car is unplugged or didn't report it.
    range_miles: Optional[int] = None
    # Battery state of health (%) from the last plug-in reading.
    soh_percent: Optional[int] = None
    # Read-only lock status and last-known GPS location from the last reading.
    is_locked: Optional[bool] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Read-only vehicle health from the last reading: 12V battery %, the SDK's
    # own warning flags, and any door/bonnet/boot reported open.
    aux_battery_percent: Optional[int] = None
    tyre_pressure_warning: Optional[bool] = None
    washer_fluid_warning: Optional[bool] = None
    key_battery_warning: Optional[bool] = None
    open_items: list[str] = field(default_factory=list)

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
    # Estimated total grid energy and cost for the session (planned slot energy ×
    # recent average price). None/0 when disconnected or the price isn't known.
    planned_energy_kwh: float = 0.0
    projected_cost: Optional[float] = None
    projected_cost_currency: Optional[str] = None
    # How projected_cost was derived: "agile" (each slot priced against the
    # half-hourly Octopus Agile rate) or "average" (flat recent £/kWh). None when
    # there's no cost. Lets the dashboard label an Agile-accurate figure.
    projected_cost_method: Optional[str] = None

    # Schedule
    slots: list[dict[str, Any]] = field(default_factory=list)
    next_slot_start: Optional[str] = None
    next_slot_end: Optional[str] = None
    # End of the last scheduled slot — when the charge is projected to finish.
    # None when disconnected or no schedule is allocated yet.
    projected_finish: Optional[str] = None
    # Ohme's own configured target ("ready-by") time as "HH:MM", read back from
    # the charge rule. Set even when unplugged (Ohme keeps a rule), so the
    # dashboard's ready-by field can auto-populate. None when no time is set.
    ohme_ready_by: Optional[str] = None

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
        # Driving range (miles) and odometer (miles) captured alongside the SOC
        # at the last plug-in. Range is shown next to the SOC; the odometer is
        # persisted per session so efficiency (mi/kWh) can be derived later.
        self.last_range_miles: Optional[int] = None
        self.last_odometer_miles: Optional[int] = None
        # Battery state of health (%) captured at the last plug-in. Logged per
        # session for a degradation trend; also shown on the dashboard.
        self.last_soh_percent: Optional[int] = None
        # Read-only lock status and last-known GPS location from the last read.
        self.last_is_locked: Optional[bool] = None
        self.last_latitude: Optional[float] = None
        self.last_longitude: Optional[float] = None
        # Read-only vehicle health from the last read (see VehicleState).
        self.last_aux_battery_percent: Optional[int] = None
        self.last_tyre_pressure_warning: Optional[bool] = None
        self.last_washer_fluid_warning: Optional[bool] = None
        self.last_key_battery_warning: Optional[bool] = None
        self.last_open_items: list[str] = []
        # Monotonic time of the last Bluelink reading, used to pace the mid-charge
        # live-SOC refresh (so it fires LIVE_SOC_INTERVAL after the plug-in read,
        # not immediately). None means no reading held yet.
        self.last_soc_at: Optional[float] = None
        # Runtime charge-target override set from the dashboard. None means "use
        # the CHARGE_TARGET env default"; see the `charge_target` property.
        self.charge_target_override: Optional[int] = None
        # Optional "ready-by" departure time as an ``HH:MM`` string. None means
        # no target time (Ohme charges on its own smart schedule). When set, it's
        # passed to Ohme so the charge completes by then.
        self.ready_by: Optional[str] = None
        # Per-weekday target overrides {0(Mon)..6(Sun): percent}. Any day not
        # present falls back to the base charge_target. Drives effective_target.
        self.day_targets: dict[int, int] = {}
        # One physical-session override for a longer journey. It takes
        # precedence over permanent/day targets and is cleared on unplug.
        self.trip_target: Optional[int] = None
        self.trip_ready_by: Optional[str] = None
        self.notification_preferences = NotificationPreferences()
        # Runtime-selected Hyundai vehicle id (when the account has more than
        # one). None means "use config.HYUNDAI_VEHICLE_ID, else the first".
        self.vehicle_id_override: Optional[str] = None
        # Most recent average price (£/kWh) and currency from a charge summary,
        # cached so build_snapshot can estimate the current session's cost
        # without its own upstream call. None until the first summary is parsed.
        self.avg_price_per_kwh: Optional[float] = None
        self.price_currency: Optional[str] = None
        # Most recent upcoming Octopus Agile half-hourly rates, cached so the
        # synchronous build_snapshot can price the session's slots against the
        # real per-slot rate. Populated by the /api/tariff fetch; None until then
        # (or when the tariff feature is disabled) — build_snapshot then falls
        # back to avg_price_per_kwh.
        self.agile_rates: Optional[list[dict]] = None
        # Why the most recent poll failed ("poll_failed", "login_failed"), or
        # None when it succeeded. Failures keep the previous snapshot so the
        # dashboard shows last-known-good data rather than going blank.
        self.last_poll_error: Optional[str] = None
        # How many polls in a row have failed. Drives the "can't reach Ohme"
        # alert (sent once when a threshold is crossed) and its recovery notice.
        self.consecutive_poll_failures: int = 0
        # True only after the outage notification was emitted, so a recovery
        # message cannot appear when problem alerts were disabled mid-outage.
        self.poll_failure_notified: bool = False
        # True once the user has been alerted that handling the current plug-in
        # is failing, so the per-poll retries don't re-notify. Cleared when a
        # plug-in is handled successfully and when the car unplugs.
        self.plugin_failure_notified: bool = False
        # Durable identity of the physically connected session. Telemetry and
        # session events use these instead of inferring boundaries from time.
        self.active_session_id: Optional[int] = None
        self.active_session_key: Optional[str] = None
        # Local date the weekly digest was last sent, so it goes out once on its
        # scheduled day rather than every poll during the digest hour. In-memory:
        # a restart within that hour could re-send once (rare, low-harm).
        self.last_digest_date: Optional[datetime.date] = None

    @property
    def charge_target(self) -> int:
        """The active charge target: the runtime override if set, else the env default."""
        return self.charge_target_override if self.charge_target_override is not None else config.CHARGE_TARGET

    def set_charge_target(self, value: int) -> None:
        """Set the runtime charge-target override (does not persist; see settings.save_target)."""
        self.charge_target_override = int(value)

    def set_ready_by(self, value: Optional[str]) -> None:
        """Set the runtime ready-by time (does not persist; see settings.save_ready_by)."""
        self.ready_by = value

    def set_day_targets(self, value: dict[int, int]) -> None:
        """Set the per-weekday target overrides (does not persist; see settings.save_day_targets)."""
        self.day_targets = dict(value)

    def set_trip_mode(self, target: int, ready_by: Optional[str]) -> None:
        self.trip_target = int(target)
        self.trip_ready_by = ready_by

    def clear_trip_mode(self) -> None:
        self.trip_target = None
        self.trip_ready_by = None

    def set_notification_preferences(self, value: NotificationPreferences) -> None:
        self.notification_preferences = value

    @property
    def trip_mode_enabled(self) -> bool:
        return self.trip_target is not None

    def set_vehicle_id(self, value: Optional[str]) -> None:
        """Set the runtime vehicle selection (does not persist; see settings.save_vehicle_id)."""
        self.vehicle_id_override = value

    @property
    def selected_vehicle_id(self) -> Optional[str]:
        """The Hyundai vehicle id to read: runtime override, else the env default, else None (first)."""
        if self.vehicle_id_override is not None:
            return self.vehicle_id_override
        return config.HYUNDAI_VEHICLE_ID or None

    @property
    def effective_target(self) -> int:
        """Trip override, then today's per-weekday override, then the base."""
        if self.trip_target is not None:
            return self.trip_target
        return self.day_targets.get(_today_weekday(), self.charge_target)

    @property
    def effective_ready_by(self) -> Optional[str]:
        """The one-session departure time when active, else the permanent one."""
        return self.trip_ready_by if self.trip_target is not None else self.ready_by

    @property
    def ready_by_tuple(self) -> Optional[tuple[int, int]]:
        """The ready-by time as an (hour, minute) tuple for the Ohme API, or None."""
        import settings  # local import to avoid a cycle at module load

        value = self.effective_ready_by
        return settings.parse_hhmm(value) if value else None

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
        self.last_soc_at = time.monotonic()

    def record_vehicle_state(self, state: Any) -> None:
        """Remember the SOC plus driving range, odometer and SoH from a Bluelink read."""
        self.last_soc = state.soc
        self.last_range_miles = state.range_miles
        self.last_odometer_miles = state.odometer_miles
        self.last_soh_percent = state.soh_percent
        self.last_is_locked = state.is_locked
        self.last_latitude = state.latitude
        self.last_longitude = state.longitude
        self.last_aux_battery_percent = state.aux_battery_percent
        self.last_tyre_pressure_warning = state.tyre_pressure_warning
        self.last_washer_fluid_warning = state.washer_fluid_warning
        self.last_key_battery_warning = state.key_battery_warning
        self.last_open_items = list(state.open_items)
        self.last_soc_at = time.monotonic()

    def clear_soc(self) -> None:
        """Forget the plug-in readings — they're stale the moment the car unplugs."""
        self.last_soc = None
        self.last_range_miles = None
        self.last_odometer_miles = None
        self.last_soh_percent = None
        self.last_is_locked = None
        self.last_latitude = None
        self.last_longitude = None
        self.last_aux_battery_percent = None
        self.last_tyre_pressure_warning = None
        self.last_washer_fluid_warning = None
        self.last_key_battery_warning = None
        self.last_open_items = []
        self.last_soc_at = None
        # New session, clean slate for the plug-in failure alert.
        self.plugin_failure_notified = False
        self.active_session_id = None
        self.active_session_key = None


# Module-level singleton imported by api.py and tests.
store = AppState()
