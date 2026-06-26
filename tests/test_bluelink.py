from unittest.mock import MagicMock, patch
import pytest
import bluelink


def _mock_manager(vehicles: dict):
    vm = MagicMock()
    vm.vehicles = vehicles
    return vm


def _mock_vehicle(soc, *, ev_range=None, ev_range_unit=None, odometer=None, odometer_unit=None, soh=None):
    v = MagicMock()
    v.ev_battery_percentage = soc
    v.ev_driving_range = ev_range
    v.ev_driving_range_unit = ev_range_unit
    v.odometer = odometer
    v.odometer_unit = odometer_unit
    v.ev_battery_soh_percentage = soh
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
