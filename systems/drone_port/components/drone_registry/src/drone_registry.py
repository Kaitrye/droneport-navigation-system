"""
DroneRegistry — компонент для учёта дронов и их состояния.
"""

from typing import Dict, Any
from systems.droneport.components.state_store.src.state_store import StateStore


class DroneRegistry:
    """Реестр дронов в дронопорту."""

    def __init__(self, state_store: StateStore):
        self.state = state_store

    def register_drone(
        self,
        drone_id: str,
        battery_level: float,
        port_id: str
    ) -> None:
        """Зарегистрировать дрон при посадке."""
        self.state.save_drone(drone_id, {
            "drone_id": drone_id,
            "port_id": port_id,
            "battery_level": str(battery_level),
            "status": "landed",
            "issues": ""
        })

    def get_drone_status(self, drone_id: str) -> Dict[str, Any]:
        """Получить статус дрона."""
        drone = self.state.get_drone(drone_id)
        if not drone:
            return {"drone_id": drone_id, "status": "not_found"}
        return drone

    def list_all_drones(self) -> list:
        """Получить список всех дронов с диагностикой."""
        drones = self.state.list_drones()
        result = []
        for d in drones:
            safety_target = "normal_operation"
            issues = []

            bat = float(d.get("battery_level", 0))
            if bat < 20.0:
                safety_target = "low_battery_alert"
                issues.append("battery_critical")

            result.append({
                "drone_id": d["drone_id"],
                "port_id": d.get("port_id", ""),
                "battery_level": bat,
                "status": d.get("status", "unknown"),
                "safety_target": safety_target,
                "issues": issues
            })
        return result