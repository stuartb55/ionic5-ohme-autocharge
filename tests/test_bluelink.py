from unittest.mock import MagicMock, patch
import pytest
import bluelink


def _mock_manager(vehicles: dict):
    vm = MagicMock()
    vm.vehicles = vehicles
    return vm


def _mock_vehicle(soc):
    v = MagicMock()
    v.ev_battery_percentage = soc
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


def test_singleton_manager_created_once():
    """_get_manager should reuse the same VehicleManager instance across calls."""
    bluelink._manager = None  # reset singleton
    with patch("bluelink.VehicleManager") as MockVM:
        MockVM.return_value.vehicles = {"vin1": _mock_vehicle(70)}
        bluelink.get_battery_percentage()
        bluelink.get_battery_percentage()
    MockVM.assert_called_once()
    bluelink._manager = None  # clean up
