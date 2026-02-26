#Простые тесты для DroneSimulator.
import pytest
from src.drone_simulator import DroneSimulator, DroneStatus


def test_create_drone():
    #Проверка создания дрона.
    drone = DroneSimulator(drone_id="test_001", initial_battery=80.0)
    state = drone.get_state()
    
    assert state["drone_id"] == "test_001"
    assert state["battery"] == 80.0
    assert state["status"] == DroneStatus.IDLE.value


def test_takeoff():
    #Проверка взлета.
    drone = DroneSimulator(drone_id="test_002", initial_battery=100.0)
    
    result = drone.takeoff(altitude=15.0)
    assert result["success"] is True
    assert drone.get_state()["status"] == DroneStatus.FLYING.value
    assert drone.get_state()["altitude"] == 15.0


def test_takeoff_low_battery():
    #Проверка взлета с низкой батареей.
    drone = DroneSimulator(drone_id="test_003", initial_battery=15.0)
    
    result = drone.takeoff()
    assert result["success"] is False
    assert "Battery too low" in result["error"]


def test_land():
    #Проверка посадки.
    drone = DroneSimulator(drone_id="test_004", initial_battery=100.0)
    drone.takeoff(altitude=10.0)
    
    result = drone.land(droneport_id="droneport_001")
    assert result["success"] is True
    assert drone.get_state()["status"] == DroneStatus.LANDED.value
    assert drone.get_state()["is_at_droneport"] is True


def test_move():
    #Проверка движения.
    drone = DroneSimulator(drone_id="test_005", initial_battery=100.0)
    drone.takeoff(altitude=10.0)
    
    result = drone.move(target_position={"x": 10.0, "y": 20.0, "z": 15.0})
    assert result["success"] is True
    assert drone.get_state()["position"]["x"] == 10.0
    assert drone.get_state()["position"]["y"] == 20.0


def test_charge():
    #Проверка зарядки.
    drone = DroneSimulator(drone_id="test_006", initial_battery=30.0)
    drone.takeoff()
    drone.land(droneport_id="droneport_001")
    
    result = drone.charge(target_level=80.0)
    assert result["success"] is True
    assert drone.get_state()["battery"] == 80.0

