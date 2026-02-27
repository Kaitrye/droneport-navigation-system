# systems/droneport/tests/unit/test_drone_registry.py
"""
Тесты компонента DroneRegistry (учёт дронов и их состояния).
"""

import pytest
from components.drone_registry.src.drone_registry import DroneRegistry


def test_register_drone(state_store):
    registry = DroneRegistry(state_store)
    
    registry.register_drone(
        drone_id="D-001",
        battery_level=50.0,
        port_id="P-01"
    )
    
    drone = registry.get_drone("D-001")
    assert drone["battery_level"] == "50.0"
    assert drone["status"] == "landed"


def test_run_diagnostics_low_battery(state_store):
    registry = DroneRegistry(state_store)
    registry.register_drone("D-001", battery_level=15.0, port_id="P-01")
    
    result = registry.run_post_landing_diagnostics("D-001")
    assert result["status"] == "diagnostics.failed"
    assert "battery_critical" in result["issues"]