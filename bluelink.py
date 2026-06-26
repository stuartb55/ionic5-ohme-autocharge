import logging
import threading
from hyundai_kia_connect_api import VehicleManager

import config

logger = logging.getLogger(__name__)

# Region 1 = Europe, Brand 2 = Hyundai
_manager: VehicleManager | None = None

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


def get_battery_percentage() -> int:
    """Return the current battery SOC % for the first vehicle on the account."""
    with _lock:
        vm = _get_manager()
        vm.check_and_refresh_token()
        vm.update_all_vehicles_with_cached_state()

        if not vm.vehicles:
            raise RuntimeError("No vehicles found on this Hyundai account")

        vehicle = next(iter(vm.vehicles.values()))
        soc = vehicle.ev_battery_percentage

    if soc is None:
        raise RuntimeError("Vehicle did not report a battery percentage — try again shortly")

    logger.info("Hyundai battery SOC: %s%%", soc)
    return soc
