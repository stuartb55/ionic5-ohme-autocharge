import time
from unittest.mock import MagicMock, patch
import pytest
import bluelink
import config


def _mock_manager(vehicles: dict):
    vm = MagicMock()
    vm.vehicles = vehicles
    return vm


def _mock_vehicle(soc, *, ev_range=None, ev_range_unit=None, odometer=None, odometer_unit=None,
                  soh=None, is_locked=None, latitude=None, longitude=None,
                  aux_battery=None, tyre_warn=None, washer_warn=None, key_warn=None,
                  open_items=None):
    v = MagicMock()
    v.ev_battery_percentage = soc
    v.ev_driving_range = ev_range
    v.ev_driving_range_unit = ev_range_unit
    v.odometer = odometer
    v.odometer_unit = odometer_unit
    v.ev_battery_soh_percentage = soh
    v.is_locked = is_locked
    v.location_latitude = latitude
    v.location_longitude = longitude
    # Vehicle health. Defaults below mirror "not reported" so existing tests
    # (which don't pass these) get None / [] for the health fields.
    v.car_battery_percentage = aux_battery
    v.tire_pressure_all_warning_is_on = tyre_warn
    v.washer_fluid_warning_is_on = washer_warn
    v.smart_key_battery_warning_is_on = key_warn
    open_set = set(open_items or [])
    v.hood_is_open = "Bonnet" in open_set
    v.trunk_is_open = "Boot" in open_set
    v.front_left_door_is_open = "Front-left door" in open_set
    v.front_right_door_is_open = "Front-right door" in open_set
    v.back_left_door_is_open = "Rear-left door" in open_set
    v.back_right_door_is_open = "Rear-right door" in open_set
    return v


def test_returns_battery_percentage():
    vm = _mock_manager({"vin1": _mock_vehicle(62)})
    with patch("bluelink._get_manager", return_value=vm):
        assert bluelink.get_battery_percentage() == 62


def test_calls_refresh_and_update_on_manager():
    vm = _mock_manager({"vin1": _mock_vehicle(50)})
    with patch("bluelink._get_manager", return_value=vm):
        bluelink.get_battery_percentage()
    vm.check_and_refresh_token.assert_called_once()
    vm.update_all_vehicles_with_cached_state.assert_called_once()


def test_raises_runtime_error_when_no_vehicles():
    vm = _mock_manager({})
    with patch("bluelink._get_manager", return_value=vm):
        with pytest.raises(RuntimeError, match="No vehicles found"):
            bluelink.get_battery_percentage()


def test_raises_runtime_error_when_soc_is_none():
    vm = _mock_manager({"vin1": _mock_vehicle(None)})
    with patch("bluelink._get_manager", return_value=vm):
        with pytest.raises(RuntimeError, match="battery percentage"):
            bluelink.get_battery_percentage()


def test_vehicle_state_converts_km_to_miles():
    vm = _mock_manager(
        {"vin1": _mock_vehicle(62, ev_range=300, ev_range_unit="km", odometer=20000, odometer_unit="km")}
    )
    with patch("bluelink._get_manager", return_value=vm):
        state = bluelink.get_vehicle_state()
    assert state.soc == 62
    assert state.range_miles == 186  # 300 km -> 186 mi
    assert state.odometer_miles == 12427  # 20000 km -> 12427 mi


def test_vehicle_state_passes_through_miles():
    vm = _mock_manager({"vin1": _mock_vehicle(50, ev_range=180, ev_range_unit="mi")})
    with patch("bluelink._get_manager", return_value=vm):
        state = bluelink.get_vehicle_state()
    assert state.range_miles == 180


def test_vehicle_state_range_none_on_unknown_unit():
    # Missing/unrecognised unit must not be guessed at — report None.
    vm = _mock_manager({"vin1": _mock_vehicle(50, ev_range=300, ev_range_unit=None)})
    with patch("bluelink._get_manager", return_value=vm):
        state = bluelink.get_vehicle_state()
    assert state.range_miles is None
    assert state.odometer_miles is None


def test_vehicle_state_reads_soh():
    vm = _mock_manager({"v": _mock_vehicle(62, soh=98)})
    with patch("bluelink._get_manager", return_value=vm):
        assert bluelink.get_vehicle_state().soh_percent == 98


def test_vehicle_state_soh_none_when_zero_or_missing():
    # 0 (and a non-numeric MagicMock default) both mean "not reported".
    vm = _mock_manager({"v": _mock_vehicle(62, soh=0)})
    with patch("bluelink._get_manager", return_value=vm):
        assert bluelink.get_vehicle_state().soh_percent is None


def test_vehicle_state_reads_lock_and_location():
    vm = _mock_manager({"v": _mock_vehicle(62, is_locked=True, latitude=51.5, longitude=-0.12)})
    with patch("bluelink._get_manager", return_value=vm):
        s = bluelink.get_vehicle_state()
    assert s.is_locked is True
    assert (s.latitude, s.longitude) == (51.5, -0.12)


def test_vehicle_state_lock_location_none_when_absent():
    # Default mock leaves these as non-numeric/non-bool MagicMocks -> None.
    vm = _mock_manager({"v": _mock_vehicle(62)})
    with patch("bluelink._get_manager", return_value=vm):
        s = bluelink.get_vehicle_state()
    assert s.is_locked is None
    assert s.latitude is None and s.longitude is None


def test_vehicle_state_reads_health():
    vm = _mock_manager({"v": _mock_vehicle(
        62, aux_battery=85, tyre_warn=True, washer_warn=False, key_warn=True,
        open_items=["Boot", "Front-left door"],
    )})
    with patch("bluelink._get_manager", return_value=vm):
        s = bluelink.get_vehicle_state()
    assert s.aux_battery_percent == 85
    assert s.tyre_pressure_warning is True
    assert s.washer_fluid_warning is False
    assert s.key_battery_warning is True
    assert s.open_items == ["Boot", "Front-left door"]


def test_vehicle_state_health_none_when_absent():
    # Default mock reports no health (aux 0/None, flags non-bool/None, nothing open).
    vm = _mock_manager({"v": _mock_vehicle(62)})
    with patch("bluelink._get_manager", return_value=vm):
        s = bluelink.get_vehicle_state()
    assert s.aux_battery_percent is None
    assert s.tyre_pressure_warning is None
    assert s.open_items == []


def test_vehicle_state_open_items_ordered_bonnet_first():
    vm = _mock_manager({"v": _mock_vehicle(62, open_items=["Front-left door", "Bonnet"])})
    with patch("bluelink._get_manager", return_value=vm):
        s = bluelink.get_vehicle_state()
    # Order follows _OPEN_ITEMS (bonnet, boot, doors…), not the input order.
    assert s.open_items == ["Bonnet", "Front-left door"]


def test_get_vehicle_state_selects_by_id():
    vm = _mock_manager({"a": _mock_vehicle(60), "b": _mock_vehicle(90)})
    with patch("bluelink._get_manager", return_value=vm):
        assert bluelink.get_vehicle_state("b").soc == 90
        assert bluelink.get_vehicle_state("missing").soc == 60  # unknown id -> first
        assert bluelink.get_vehicle_state().soc == 60  # None -> first


def test_list_vehicles_maps_fields():
    v = _mock_vehicle(60)
    v.id, v.name, v.VIN, v.model = "a", "IONIQ 5", "VIN1", "IONIQ 5"
    vm = _mock_manager({"a": v})
    with patch("bluelink._get_manager", return_value=vm):
        assert bluelink.list_vehicles() == [
            {"id": "a", "name": "IONIQ 5", "vin": "VIN1", "model": "IONIQ 5"}
        ]


def test_singleton_manager_created_once():
    """_get_manager should reuse the same VehicleManager instance across calls."""
    bluelink._manager = None  # reset singleton
    with patch("bluelink.VehicleManager") as MockVM:
        MockVM.return_value.vehicles = {"vin1": _mock_vehicle(70)}
        bluelink.get_battery_percentage()
        bluelink.get_battery_percentage()
    MockVM.assert_called_once()
    bluelink._manager = None  # clean up


async def test_get_vehicle_state_async_returns_state():
    vm = _mock_manager({"vin1": _mock_vehicle(62)})
    with patch("bluelink._get_manager", return_value=vm):
        state = await bluelink.get_vehicle_state_async()
    assert state.soc == 62


async def test_get_vehicle_state_async_times_out(monkeypatch):
    """A slow SDK read must not hang the caller — wait_for raises TimeoutError."""
    monkeypatch.setattr(config, "UPSTREAM_TIMEOUT", 0.05)

    def slow(_vehicle_id):
        time.sleep(0.3)
        return bluelink.VehicleState(soc=50)

    monkeypatch.setattr(bluelink, "get_vehicle_state", slow)
    with pytest.raises(TimeoutError):
        await bluelink.get_vehicle_state_async()


async def test_list_vehicles_async_returns_list(monkeypatch):
    monkeypatch.setattr(bluelink, "list_vehicles", lambda: [{"id": "a"}])
    assert await bluelink.list_vehicles_async() == [{"id": "a"}]
