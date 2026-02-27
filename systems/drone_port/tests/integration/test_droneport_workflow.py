# systems/droneport/tests/integration/test_droneport_workflow.py
"""
Интеграционный тест: полный цикл взаимодействия НУС ↔ Дронопорт.
"""

import pytest
from systems.drone_port.src.droneport_system import DroneportSystem
from shared.topics import DroneportActions


def test_full_lifecycle(mock_bus, state_store):
    """Сценарий: резервирование → preflight → зарядка → взлёт → посадка → диагностика."""
    
    # Создаём систему с моками
    droneport = DroneportSystem(
        system_id="test-droneport",
        name="TestDroneport",
        bus=mock_bus,
        state_store=state_store  # внедряем через конструктор
    )
    
    # 1. Резервирование слота
    reserve_msg = {
        "message_id": "msg-1",
        "timestamp": "2026-02-27T12:00:00Z",
        "payload": {
            "mission_id": "m-123",
            "drone_ids": ["D-001"],
            "mission_window": {"start": "2026-02-27T12:10:00Z", "end": "2026-02-27T13:00:00Z"}
        }
    }
    result = droneport._handle_reserve_slots(reserve_msg)
    assert result["status"] == "reserved"
    
    # 2. Preflight check
    preflight_msg = {
        "message_id": "msg-2",
        "payload": {"drone_id": "D-001"}
    }
    result = droneport._handle_preflight_check(preflight_msg)
    assert result["status"] == "preflight.ok"
    
    # 3. Зарядка
    charge_msg = {
        "message_id": "msg-3",
        "payload": {"drone_id": "D-001", "min_battery": 90.0}
    }
    result = droneport._handle_charge_to_threshold(charge_msg)
    assert result["status"] == "charge.completed"
    
    # 4. Посадка и диагностика
    dock_msg = {
        "message_id": "msg-4",
        "payload": {"drone_id": "D-001"}
    }
    result = droneport._handle_dock(dock_msg)
    assert result["status"] == "docked"
    
    # Проверяем, что запустилась диагностика
    diagnostics = droneport.drone_registry.run_post_landing_diagnostics("D-001")
    assert "status" in diagnostics