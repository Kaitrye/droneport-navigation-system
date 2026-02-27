"""
PortManager — компонент для резервирования и освобождения посадочных площадок.
"""

from typing import Dict, Any, List
from systems.droneport.components.state_store.src.state_store import StateStore


class PortManager:
    """Управление посадочными площадками дронопорта."""

    def __init__(self, state_store: StateStore):
        self.state = state_store

    def reserve_slot(
        self,
        drone_id: str,
        port_id: str,
        mission_window: Dict[str, str]
    ) -> Dict[str, Any]:
        """Зарезервировать слот для дрона."""
        if self.state.is_port_occupied(port_id):
            return {
                "status": "rejected",
                "reason": f"Port {port_id} is already occupied",
                "error_code": "PORT_RESOURCE_BUSY",
                "retryable": False
            }

        # Сохраняем площадку
        self.state.save_port(port_id, {
            "port_id": port_id,
            "drone_id": drone_id,
            "status": "reserved",
            "mission_window_start": mission_window.get("start", ""),
            "mission_window_end": mission_window.get("end", "")
        })

        # Регистрируем дрон как ожидающего посадки
        self.state.save_drone(drone_id, {
            "drone_id": drone_id,
            "port_id": port_id,
            "status": "reserved",
            "battery_level": "0.0"
        })

        return {
            "status": "reserved",
            "port_id": port_id,
            "drone_id": drone_id
        }

    def release_for_takeoff(self, drone_id: str) -> Dict[str, Any]:
        """Освободить площадку после взлёта."""
        drone = self.state.get_drone(drone_id)
        if not drone:
            return {"status": "failed", "reason": "Drone not found"}

        port_id = drone.get("port_id")
        if port_id:
            self.state.save_port(port_id, {
                "port_id": port_id,
                "drone_id": "",
                "status": "free"
            })
            self.state.delete_drone(drone_id)

        return {"status": "release_ack", "drone_id": drone_id}

    def request_landing_slot(self, drone_id: str, preferred_ports: List[str] = None) -> Dict[str, Any]:
        """Запросить слот для посадки (упрощённо — первый свободный)."""
        # В реальности можно искать по списку или по ближайшей площадке
        all_ports = ["P-01", "P-02", "P-03", "P-04"]  # можно вынести в конфиг
        for port_id in all_ports:
            if not self.state.is_port_occupied(port_id):
                return {
                    "status": "slot_assigned",
                    "port_id": port_id,
                    "drone_id": drone_id
                }

        return {
            "status": "denied",
            "reason": "No available slots",
            "error_code": "PORT_RESOURCE_BUSY",
            "retryable": True
        }