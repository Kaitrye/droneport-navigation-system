# systems/droneport/tests/unit/test_battery_charger.py
"""
Тесты компонента BatteryCharger (управление зарядкой).
"""

import pytest
from components.battery_charger.src.battery_charger import BatteryCharger


def test_charge_to_threshold_success(state_store):
    charger = BatteryCharger(state_store)
    
    result = charger.charge_to_threshold(
        drone_id="D-001",
        min_battery=90.0,
        current_battery=40.0,
        departure_time_sec=3600
    )
    
    assert result["status"] == "charge.completed"
    assert result["charging_power_w"] > 0


def test_charge_already_sufficient(state_store):
    charger = BatteryCharger(state_store)
    
    result = charger.charge_to_threshold(
        drone_id="D-001",
        min_battery=80.0,
        current_battery=85.0,
        departure_time_sec=3600
    )
    
    assert result["status"] == "charge.not_required"