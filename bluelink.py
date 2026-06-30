import asyncio
import logging
import threading
from dataclasses import dataclass, field
from typing import Optional

from hyundai_kia_connect_api import VehicleManager

import config

logger = logging.getLogger(__name__)

# Region 1 = Europe, Brand 2 = Hyundai
_manager: VehicleManager | None = None

# The SDK reports distances in the account's configured unit ("km", "mi", or
# None). This app is UK-only, so normalise everything to miles for display.
_KM_TO_MILES = 0.621371


@dataclass
class VehicleState:
    """A snapshot of the vehicle read from Bluelink at a point in time.

    ``range_miles`` and ``odometer_miles`` are None when the vehicle didn't
    report them (or reported an unrecognised unit) — they're nice-to-haves, so a
    missing value must never block the SOC the charging logic depends on.
    """

    soc: int
    range_miles: Optional[int] = None
    odometer_miles: Optional[int] = None
    # Battery state of health (%). None when the vehicle doesn't report it.
    soh_percent: Optional[int] = None
    # Read-only lock status and last-known GPS location. None when not reported.
    is_locked: Optional[bool] = None
    latitude: Optional[float] = None
    longitude: Optional[float] = None
    # Read-only vehicle health (all best-effort). aux_battery_percent is the 12V
    # auxiliary battery %; the *_warning flags mirror the SDK's own warnings
    # (None when the car doesn't report them); open_items lists any door/bonnet/
    # boot the car reports as open (empty when all closed or not reported).
    aux_battery_percent: Optional[int] = None
    tyre_pressure_warning: Optional[bool] = None
    washer_fluid_warning: Optional[bool] = None
    key_battery_warning: Optional[bool] = None
    open_items: list[str] = field(default_factory=list)


# SDK "is open" attribute -> human label, for the "left open" health chip. Order
# is the order they're listed to the user.
_OPEN_ITEMS = (
    ("hood_is_open", "Bonnet"),
    ("trunk_is_open", "Boot"),
    ("front_left_door_is_open", "Front-left door"),
    ("front_right_door_is_open", "Front-right door"),
    ("back_left_door_is_open", "Rear-left door"),
    ("back_right_door_is_open", "Rear-right door"),
)


def _as_bool(value) -> Optional[bool]:
    """Coerce an SDK warning flag to a real bool, else None.

    The flags are bools when reported, but can be absent or a non-bool (and are
    MagicMocks in tests), so only a genuine bool is trusted — anything else is
    "not reported" rather than a misleading False/True.
    """
    return value if isinstance(value, bool) else None


def _open_items(vehicle) -> list[str]:
    """Labels for any door/bonnet/boot the car reports as open (strictly True)."""
    return [label for attr, label in _OPEN_ITEMS if getattr(vehicle, attr, None) is True]


def _to_miles(value, unit) -> Optional[int]:
    """Convert an SDK distance (value + unit string) to whole miles, or None.

    Defensive: the SDK fields can be absent or non-numeric (and in tests are
    MagicMocks), so anything that isn't a real number in a known unit yields
    None rather than a wrong reading.
    """
    try:
        miles = float(value)
    except (TypeError, ValueError):
        return None
    if unit == "km":
        miles *= _KM_TO_MILES
    elif unit != "mi":
        # Unknown/absent unit — don't guess at the scale.
        return None
    return round(miles)

# The VehicleManager is a shared, mutable singleton and the SDK is not
# thread-safe. get_battery_percentage runs via asyncio.to_thread and has two
# concurrent callers — the poll loop's plug-in handler and the dashboard's
# "save target" reapply — so serialise every access to the manager here to stop
# two threads refreshing tokens / vehicle state on the same object at once.
_lock = threading.Lock()


def _get_manager() -> VehicleManager:
    global _manager
    if _manager is None:
        _manager = VehicleManager(
            region=1,
            brand=2,
            username=config.HYUNDAI_USERNAME,
            password=config.HYUNDAI_PASSWORD,
            pin=config.HYUNDAI_PIN,
        )
    return _manager


def _select_vehicle(vm: VehicleManager, vehicle_id: Optional[str]):
    """Pick the configured vehicle by id, falling back to the first one."""
    if vehicle_id and vehicle_id in vm.vehicles:
        return vm.vehicles[vehicle_id]
    return next(iter(vm.vehicles.values()))


def list_vehicles() -> list[dict]:
    """Return all vehicles on the account as {id, name, vin, model} dicts."""
    with _lock:
        vm = _get_manager()
        vm.check_and_refresh_token()
        vm.update_all_vehicles_with_cached_state()
        return [
            {"id": v.id, "name": v.name, "vin": v.VIN, "model": v.model}
            for v in vm.vehicles.values()
        ]


def get_vehicle_state(vehicle_id: Optional[str] = None) -> VehicleState:
    """Return SOC (plus driving range and odometer) for the selected vehicle.

    ``vehicle_id`` picks a specific vehicle when the account has more than one;
    when None (or unknown) the first vehicle is used. SOC is required — a missing
    one raises, since the charging logic can't proceed without it. Range and
    odometer are best-effort extras.
    """
    with _lock:
        vm = _get_manager()
        vm.check_and_refresh_token()
        vm.update_all_vehicles_with_cached_state()

        if not vm.vehicles:
            raise RuntimeError("No vehicles found on this Hyundai account")

        vehicle = _select_vehicle(vm, vehicle_id)
        soc = vehicle.ev_battery_percentage
        range_miles = _to_miles(vehicle.ev_driving_range, vehicle.ev_driving_range_unit)
        odometer_miles = _to_miles(vehicle.odometer, vehicle.odometer_unit)
        raw_soh = vehicle.ev_battery_soh_percentage
        # SoH is a percentage; 0/None/non-numeric means "not reported".
        soh_percent = int(raw_soh) if isinstance(raw_soh, (int, float)) and raw_soh > 0 else None
        is_locked = vehicle.is_locked if isinstance(vehicle.is_locked, bool) else None
        lat, lon = vehicle.location_latitude, vehicle.location_longitude
        latitude = float(lat) if isinstance(lat, (int, float)) else None
        longitude = float(lon) if isinstance(lon, (int, float)) else None

        raw_aux = getattr(vehicle, "car_battery_percentage", None)
        # 12V battery; 0/None/non-numeric means "not reported".
        aux_battery_percent = (
            int(raw_aux) if isinstance(raw_aux, (int, float)) and raw_aux > 0 else None
        )
        tyre_pressure_warning = _as_bool(getattr(vehicle, "tire_pressure_all_warning_is_on", None))
        washer_fluid_warning = _as_bool(getattr(vehicle, "washer_fluid_warning_is_on", None))
        key_battery_warning = _as_bool(getattr(vehicle, "smart_key_battery_warning_is_on", None))
        open_items = _open_items(vehicle)

    if soc is None:
        raise RuntimeError("Vehicle did not report a battery percentage — try again shortly")

    logger.info(
        "Hyundai SOC: %s%%, range: %s mi, odometer: %s mi, SoH: %s%%, locked: %s, 12V: %s%%",
        soc, range_miles, odometer_miles, soh_percent, is_locked, aux_battery_percent,
    )
    return VehicleState(
        soc=soc, range_miles=range_miles, odometer_miles=odometer_miles, soh_percent=soh_percent,
        is_locked=is_locked, latitude=latitude, longitude=longitude,
        aux_battery_percent=aux_battery_percent, tyre_pressure_warning=tyre_pressure_warning,
        washer_fluid_warning=washer_fluid_warning, key_battery_warning=key_battery_warning,
        open_items=open_items,
    )


def get_battery_percentage(vehicle_id: Optional[str] = None) -> int:
    """Return just the current battery SOC % for the selected vehicle."""
    return get_vehicle_state(vehicle_id).soc


async def get_vehicle_state_async(vehicle_id: Optional[str] = None) -> VehicleState:
    """Run the blocking :func:`get_vehicle_state` in a worker thread, bounded by
    ``config.UPSTREAM_TIMEOUT``.

    Raises ``TimeoutError`` if the SDK call doesn't return in time, so a hung
    Bluelink request can't stall the poll loop (callers already treat a failed
    read as skip-and-retry). The timed-out worker thread keeps running until the
    SDK call eventually returns — ``wait_for`` only frees the async caller — which
    is acceptable: the module lock is released when that thread finishes and the
    next read re-acquires it.
    """
    return await asyncio.wait_for(
        asyncio.to_thread(get_vehicle_state, vehicle_id), config.UPSTREAM_TIMEOUT
    )


async def list_vehicles_async() -> list[dict]:
    """Async wrapper around :func:`list_vehicles`, bounded by ``config.UPSTREAM_TIMEOUT``."""
    return await asyncio.wait_for(asyncio.to_thread(list_vehicles), config.UPSTREAM_TIMEOUT)
