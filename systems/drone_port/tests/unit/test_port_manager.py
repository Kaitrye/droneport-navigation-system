# systems/droneport/tests/unit/test_port_manager.py
"""
Тесты компонента PortManager (резервирование и освобождение площадок).
"""

import pytest
from components.port_manager.src.port_manager import PortManager


def test_reserve_slot_success(state_store):
    port_manager = PortManager(state_store)
    
    result = port_manager.reserve_slot(
        drone_id="D-001",
        port_id="P-01",
        mission_window={"start": "2026-02-27T12:00:00Z", "end": "2026-02-27T13:00:00Z"}
    )
    
    assert result["status"] == "reserved"
    assert result["port_id"] == "P-01"


def test_reserve_slot_already_occupied(state_store):
    port_manager = PortManager(state_store)
    
    # Сначала занять порт
    port_manager.reserve_slot("D-001", "P-01", {})
    
    # Попытка занять снова
    result = port_manager.reserve_slot("D-002", "P-01", {})
    assert result["status"] == "rejected"
    assert "reason" in result