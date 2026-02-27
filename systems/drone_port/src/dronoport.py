"""
DroneportSystem — система управления дронопортом для агродронов.
Реализует базовые функции:
- Регистрация/удаление дронов в парке
- Генерация списка дронов с целями безопасности
- Диагностика перед вылетом и после возврата (уровень заряда, неисправности)
- Оптимизация зарядки с учётом времени вылета и мощности подключения

Это учебный скелет: бизнес-логика минимальна и может расширяться в рамках лабораторных работ.
"""

from typing import Dict, Any, Optional, List
from shared.base_system import BaseSystem
from shared.topics import SystemTopics, DroneportActions
from broker.system_bus import SystemBus
import logging

# Настройка логгера
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DroneportSystem(BaseSystem):
    """Реализация Дронопорта как SystemBus-сервиса."""

    def __init__(
        self,
        system_id: str,
        name: str,
        bus: SystemBus,
        health_port: Optional[int] = None,
    ):
        super().__init__(
            system_id=system_id,
            system_type="droneport",
            topic=SystemTopics.DRONEPORT,
            bus=bus,
            health_port=health_port,
        )
        self.name = name
        logger.info(f"DroneportSystem '{name}' initialized")

        # Простейшее in-memory хранилище дронов и портов
        self._drones: Dict[str, Dict[str, Any]] = {}  # drone_id → {status, battery, last_check, ...}
        self._ports: Dict[str, Dict[str, Any]] = {}   # port_id → {drone_id, charging_power_w, status}

    # ======================== Регистрация обработчиков ========================
    def _register_handlers(self) -> None:
        """Регистрация обработчиков для действий Дронопорта."""
        self.register_handler(DroneportActions.REQUEST_LANDING, self._handle_request_landing)
        self.register_handler(DroneportActions.REQUEST_TAKEOFF, self._handle_request_takeoff)
        self.register_handler(DroneportActions.START_CHARGING, self._handle_start_charging)
        self.register_handler(DroneportActions.STOP_CHARGING, self._handle_stop_charging)
        self.register_handler(DroneportActions.GET_PORT_STATUS, self._handle_get_port_status)

    # ======================== Обработчики действий ===========================

    def _handle_request_landing(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ОФ1. Проверка запроса и добавление нового дрона в парк.
        Payload: {"drone_id": str, "port_id": str, "battery_level": float (0..100)}
        Returns: {"drone_id": str, "port_id": str, "status": "landed", "message": str}
        """
        payload = message.get("payload", {})
        drone_id = payload.get("drone_id")
        port_id = payload.get("port_id")
        battery = payload.get("battery_level", 50.0)

        if not drone_id:
            return {"error": "drone_id_required", "status": "rejected"}
        if not port_id:
            return {"error": "port_id_required", "status": "rejected"}

        # Проверка: порт свободен?
        if port_id in self._ports and self._ports[port_id].get("drone_id"):
            return {
                "drone_id": drone_id,
                "port_id": port_id,
                "status": "rejected",
                "message": f"Port {port_id} is occupied",
            }

        # Добавляем дрона в парк
        self._drones[drone_id] = {
            "drone_id": drone_id,
            "port_id": port_id,
            "battery_level": float(battery),
            "status": "landed",
            "last_landing_time": self._get_timestamp(),
            "issues": [],
        }

        # Занимаем порт
        self._ports[port_id] = {
            "drone_id": drone_id,
            "charging_power_w": 0.0,
            "status": "occupied",
            "last_update": self._get_timestamp(),
        }

        logger.info(f"Drone {drone_id} landed at port {port_id}, battery={battery}%")
        return {
            "drone_id": drone_id,
            "port_id": port_id,
            "status": "landed",
            "message": "Landing accepted",
        }

    def _handle_request_takeoff(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ОФ2. Удаление дрона из парка (после разрешения вылета).
        Payload: {"drone_id": str}
        Returns: {"drone_id": str, "status": "takeoff_approved", "battery_level": float}
        """
        payload = message.get("payload", {})
        drone_id = payload.get("drone_id")

        if not drone_id or drone_id not in self._drones:
            return {"drone_id": drone_id, "status": "not_found"}

        drone = self._drones[drone_id]
        port_id = drone["port_id"]

        # Освобождаем порт
        if port_id in self._ports:
            del self._ports[port_id]

        # Удаляем дрона из парка
        del self._drones[drone_id]

        logger.info(f"Drone {drone_id} took off from port {port_id}")
        return {
            "drone_id": drone_id,
            "status": "takeoff_approved",
            "battery_level": drone["battery_level"],
        }

    def _handle_start_charging(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ПРФ1. Оптимизация зарядки: учитываем время вылета и мощность подключения.
        Payload: {"drone_id": str, "target_battery": float (0..100), "departure_time_sec": int}
        Returns: {"drone_id": str, "charging_power_w": float, "estimated_finish_sec": int}
        """
        payload = message.get("payload", {})
        drone_id = payload.get("drone_id")
        target_bat = payload.get("target_battery", 90.0)
        dep_time = payload.get("departure_time_sec", 3600)  # default: 1 hour

        if not drone_id or drone_id not’t in self._drones:
            return {"error": "drone_not_found", "status": "rejected"}

        drone = self._drones[drone_id]
        current_bat = drone["battery_level"]
        if current_bat >= target_bat:
            return {
                "drone_id": drone_id,
                "status": "already_sufficient",
                "battery_level": current_bat,
            }

        # Простая модель: мощность заряда = (цель - текущий) * 10 Вт / %, но ≤ 1000 Вт
        delta_bat = target_bat - current_bat
        required_energy_wh = delta_bat * 0.01 * 10  # условная ёмкость батареи = 10 Wh
        # Максимальная мощность порта — 500 Вт (можно сделать конфигурируемой позже)
        max_power_w = 500.0
        charging_power_w = min(max_power_w, required_energy_wh * 3600 / dep_time)  # Wh → W = Wh / h

        estimated_finish_sec = int(required_energy_wh * 3600 / charging_power_w) if charging_power_w > 0 else 0

        # Обновляем порт
        port_id = drone["port_id"]
        if port_id in self._ports:
            self._ports[port_id]["charging_power_w"] = charging_power_w
            self._ports[port_id]["status"] = "charging"

        # Обновляем дрона
        drone["charging_power_w"] = charging_power_w
        drone["target_battery"] = target_bat
        drone["estimated_finish_sec"] = estimated_finish_sec

        logger.info(
            f"Charging started for drone {drone_id}: "
            f"{charging_power_w:.0f}W → {target_bat}% in {estimated_finish_sec}s"
        )
        return {
            "drone_id": drone_id,
            "charging_power_w": charging_power_w,
            "estimated_finish_sec": estimated_finish_sec,
            "status": "charging_started",
        }

    def _handle_stop_charging(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """Остановка зарядки."""
        payload = message.get("payload", {})
        drone_id = payload.get("drone_id")

        if not drone_id or drone_id not in self._drones:
            return {"error": "drone_not_found", "status": "rejected"}

        port_id = self._drones[drone_id]["port_id"]
        if port_id in self._ports:
            self._ports[port_id]["charging_power_w"] = 0.0
            self._ports[port_id]["status"] = "idle"

        logger.info(f"Charging stopped for drone {drone_id}")
        return {"drone_id": drone_id, "status": "charging_stopped"}

    def _handle_get_port_status(
        self, message: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        ОФ3. Генерация списка всех дронов, их целей безопасности и состояния.
        Payload: {"filter": "all"|"landed"|"charging"} (опционально)
        Returns: {"drones": List[Dict], "total": int}
        """
        payload = message.get("payload", {})
        filter_by = payload.get("filter", "all")

        drones_list: List[Dict[str, Any]] = []
        for drone in self._drones.values():
            # ОФ4: диагностика — добавляем поля safety_target и issues
            safety_target: str = "normal_operation"
            if drone["battery_level"] < 20:
                safety_target = "low_battery_alert"
                drone["issues"].append("battery_critical")
            if drone.get("charging_power_w", 0) == 0 and drone["status"] == "landed":
                safety_target = "waiting_for_charge"

            drones_list.append({
                "drone_id": drone["drone_id"],
                "port_id": drone["port_id"],
                "battery_level": drone["battery_level"],
                "status": drone["status"],
                "safety_target": safety_target,
                "issues": drone.get("issues", []),
                "last_landing_time": drone.get("last_landing_time"),
                "charging_power_w": drone.get("charging_power_w", 0.0),
            })

        if filter_by == "landed":
            drones_list = [d for d in drones_list if d["status"] == "landed"]
        elif filter_by == "charging":
            drones_list = [d for d in drones_list if d["charging_power_w"] > 0]

        return {
            "drones": drones_list,
            "total": len(drones_list),
            "timestamp": self._get_timestamp(),
        }

    # ======================== Вспомогательные методы =========================

    def _get_timestamp(self) -> float:
        """Возвращает Unix timestamp (в секундах). Для учебного прототипа — просто time.time()."""
        import time
        return time.time()

    # ======================== Расширенный статус системы ======================

    def get_status(self) -> Dict[str, Any]:
        """Расширенный статус системы (для healthcheck и мониторинга)."""
        status = super().get_status()
        status.update(
            {
                "name": self.name,
                "drones_total": len(self._drones),
                "ports_total": len(self._ports),
                "ports_occupied": sum(1 for p in self._ports.values() if p.get("drone_id")),
                "charging_active": sum(1 for p in self._ports.values() if p.get("charging_power_w", 0) > 0),
            }
        )
        return status