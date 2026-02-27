"""
BatteryCharger — компонент для управления зарядкой дронов.
"""

from typing import Dict, Any
from systems.droneport.components.state_store.src.state_store import StateStore


class BatteryCharger:
    """Управление зарядкой дронов."""

    def __init__(self, state_store: StateStore):
        self.state = state_store

    def charge_to_threshold(
        self,
        drone_id: str,
        min_battery: float,
        current_battery: float,
        departure_time_sec: int = 3600
    ) -> Dict[str, Any]:
        """Довести заряд до порога."""
        if current_battery >= min_battery:
            return {
                "status": "charge.not_required",
                "drone_id": drone_id,
                "battery_level": str(current_battery)
            }

        # Простая модель расчёта мощности
        delta_bat = min_battery - current_battery
        required_energy_wh = delta_bat * 0.1  # условная ёмкость
        max_power_w = 500.0
        charging_power_w = min(max_power_w, required_energy_wh * 3600 / departure_time_sec)

        # Обновляем состояние дрона
        drone = self.state.get_drone(drone_id)
        if drone:
            drone.update({
                "charging_power_w": str(charging_power_w),
                "target_battery": str(min_battery),
                "status": "charging"
            })
            self.state.save_drone(drone_id, drone)

        return {
            "status": "charge.completed",
            "drone_id": drone_id,
            "charging_power_w": charging_power_w,
            "estimated_finish_sec": int(required_energy_wh * 3600 / charging_power_w) if charging_power_w > 0 else 0
        }

    def stop_charging(self, drone_id: str) -> Dict[str, Any]:
        """Остановить зарядку."""
        drone = self.state.get_drone(drone_id)
        if drone:
            drone["charging_power_w"] = "0.0"
            drone["status"] = "landed"
            self.state.save_drone(drone_id, drone)
        return {"status": "charging.stopped", "drone_id": drone_id}