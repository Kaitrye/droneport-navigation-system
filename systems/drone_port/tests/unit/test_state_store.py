# systems/droneport/tests/unit/test_state_store.py
"""
Тесты компонента StateStore (хранение состояния в Redis).
"""

import pytest
from components.state_store.src.state_store import StateStore


def test_save_and_get_drone(state_store):
    drone_data = {
        "drone_id": "D-001",
        "battery_level": "45.0",
        "status": "landed"
    }
    
    state_store.save_drone("D-001", drone_data)
    retrieved = state_store.get_drone("D-001")
    
    assert retrieved == drone_data


def test_list_drones_empty(state_store):
    drones = state_store.list_drones()
    assert drones == []


def test_list_drones_with_data(state_store, mock_redis):
    mock_redis.keys.return_value = ["drone:D-001", "drone:D-002"]
    mock_redis.hgetall.side_effect = [
        {"drone_id": "D-001", "battery_level": "30.0"},
        {"drone_id": "D-002", "battery_level": "80.0"}
    ]
    
    drones = state_store.list_drones()
    assert len(drones) == 2
    assert drones[0]["drone_id"] == "D-001"