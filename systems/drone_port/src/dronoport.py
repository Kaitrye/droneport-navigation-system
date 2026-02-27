"""
DroneportSystem — система управления дронопортом для агродронов.

Реализует интеграционный контракт с RobotSystem (НУС) согласно DronePort.md:
- Подготовка БВС к миссии (резервирование, preflight, зарядка)
- Поддержка запуска/посадки в штатном и аварийном режимах
- Передача статусов инфраструктуры

Архитектура:
- Система оркестрирует работу компонентов:
  - PortManager — управление слотами
  - BatteryCharger — зарядка до порога
  - DroneRegistry — учёт состояния дронов
  - StateStore — хранение в Redis
- Все входящие команды обрабатываются через SystemBus
"""

from typing import Dict, Any, Optional, List
from shared.base_system import BaseSystem
from shared.topics import SystemTopics, DroneportActions
from broker.system_bus import SystemBus
import logging
import time

# Импорты компонентов (должны быть реализованы в components/)
try:
    from components.state_store.src.state_store import StateStore
    from components.port_manager.src.port_manager import PortManager
    from components.battery_charger.src.battery_charger import BatteryCharger
    from components.drone_registry.src.drone_registry import DroneRegistry
except ImportError as e:
    logging.warning(f"Component import failed (running in dev mode?): {e}")
    # Для учебного запуска можно временно заменить на mock-реализации
    StateStore = PortManager = BatteryCharger = DroneRegistry = None


logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


class DroneportSystem(BaseSystem):
    """Система Дронопорта как сервис на SystemBus."""

    def __init__(
        self,
        system_id: str,
        name: str,
        bus: SystemBus,
        health_port: Optional[int] = None,
        redis_host: str = "localhost",
        redis_port: int = 6379,
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

        # Инициализация компонентов
        if StateStore is not None:
            self.state_store = StateStore(host=redis_host, port=redis_port)
            self.port_manager = PortManager(self.state_store)
            self.battery_charger = BatteryCharger(self.state_store)
            self.drone_registry = DroneRegistry(self.state_store)
        else:
            # fallback для демонстрации без компонентов
            logger.warning("Running in fallback mode (in-memory storage)")
            self._drones: Dict[str, Dict[str, Any]] = {}
            self._ports: Dict[str, Dict[str, Any]] = {}

    def _register_handlers(self) -> None:
        """Регистрация обработчиков команд от НУС."""
        self.register_handler(DroneportActions.RESERVE_SLOTS, self._handle_reserve_slots)
        self.register_handler(DroneportActions.PREFLIGHT_CHECK, self._handle_preflight_check)
        self.register_handler(DroneportActions.CHARGE_TO_THRESHOLD, self._handle_charge_to_threshold)
        self.register_handler(DroneportActions.RELEASE_FOR_TAKEOFF, self._handle_release_for_takeoff)
        self.register_handler(DroneportActions.REQUEST_LANDING_SLOT, self._handle_request_landing_slot)
        self.register_handler(DroneportActions.DOCK, self._handle_dock)
        self.register_handler(DroneportActions.EMERGENCY_RECEIVE, self._handle_emergency_receive)
        self.register_handler(DroneportActions.HEALTH_CHECK, self._handle_health_check)

    def _create_response(
        self,
        original_message: Dict[str, Any],
        status: str,
        payload: Optional[Dict[str, Any]] = None,
        error_code: Optional[str] = None,
        reason: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Унифицированный формат ответа по контракту DronePort.md."""
        response = {
            "message_id": original_message.get("message_id", f"resp_{int(time.time())}"),
            "timestamp": self._get_iso_timestamp(),
            "status": status,
        }
        if payload:
            response["payload"] = payload
        if error_code:
            response["error_code"] = error_code
            response["reason"] = reason or ""
            response["retryable"] = error_code not in ("INTERNAL_ERROR", "PORT_UNAVAILABLE")
        return response

    def _get_iso_timestamp(self) -> str:
        """Возвращает текущее время в ISO 8601."""
        return time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime())

    # ==================== Обработчики команд ====================

    def _handle_reserve_slots(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды reserve_slots."""
        try:
            payload = message.get("payload", {})
            drone_ids: List[str] = payload.get("drone_ids", [])
            mission_window = payload.get("mission_window", {})

            if not drone_ids:
                return self._create_response(
                    message, "rejected", error_code="INVALID_REQUEST", reason="drone_ids required"
                )

            # Проверка доступности слотов
            available = all(self.port_manager.is_port_available(did) for did in drone_ids)
            if not available:
                return self._create_response(
                    message, "rejected", error_code="PORT_RESOURCE_BUSY", reason="No available slots"
                )

            # Резервирование
            for drone_id in drone_ids:
                self.port_manager.reserve_port(drone_id, mission_window)

            return self._create_response(message, "reserved", payload={"slots": drone_ids})
        except Exception as e:
            logger.error(f"Error in reserve_slots: {e}")
            return self._create_response(
                message, "rejected", error_code="INTERNAL_ERROR", reason=str(e)
            )

    def _handle_preflight_check(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды preflight_check."""
        try:
            payload = message.get("payload", {})
            drone_id = payload.get("drone_id")
            if not drone_id:
                return self._create_response(
                    message, "preflight.failed", error_code="INVALID_REQUEST", reason="drone_id required"
                )

            # Простая проверка: дрон должен быть зарегистрирован и иметь батарею > 20%
            drone = self.drone_registry.get_drone(drone_id)
            if not drone or float(drone.get("battery_level", 0)) < 20.0:
                return self._create_response(
                    message, "preflight.failed", error_code="PORT_PRECHECK_FAILED", reason="Low battery"
                )

            return self._create_response(message, "preflight.ok")
        except Exception as e:
            logger.error(f"Error in preflight_check: {e}")
            return self._create_response(
                message, "preflight.failed", error_code="INTERNAL_ERROR", reason=str(e)
            )

    def _handle_charge_to_threshold(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды charge_to_threshold."""
        try:
            payload = message.get("payload", {})
            drone_id = payload.get("drone_id")
            min_battery = float(payload.get("min_battery", 80.0))

            if not drone_id:
                return self._create_response(
                    message, "failed", error_code="INVALID_REQUEST", reason="drone_id required"
                )

            result = self.battery_charger.charge_to_threshold(drone_id, min_battery)
            if result["success"]:
                return self._create_response(message, "charge.completed")
            else:
                return self._create_response(
                    message, "charge.timeout", error_code="PORT_CHARGE_TIMEOUT", reason=result.get("reason", "")
                )
        except Exception as e:
            logger.error(f"Error in charge_to_threshold: {e}")
            return self._create_response(
                message, "failed", error_code="INTERNAL_ERROR", reason=str(e)
            )

    def _handle_release_for_takeoff(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды release_for_takeoff."""
        return self._create_response(message, "release_ack")

    def _handle_request_landing_slot(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды request_landing_slot."""
        try:
            payload = message.get("payload", {})
            drone_id = payload.get("drone_id")
            if not drone_id:
                return self._create_response(
                    message, "denied", error_code="INVALID_REQUEST", reason="drone_id required"
                )

            if self.port_manager.is_port_available(drone_id):
                self.port_manager.assign_landing_slot(drone_id)
                return self._create_response(message, "slot_assigned")
            else:
                return self._create_response(
                    message, "denied", error_code="PORT_RESOURCE_BUSY", reason="No slot available"
                )
        except Exception as e:
            logger.error(f"Error in request_landing_slot: {e}")
            return self._create_response(
                message, "denied", error_code="INTERNAL_ERROR", reason=str(e)
            )

    def _handle_dock(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка команды dock + запуск пост-обработки."""
        try:
            payload = message.get("payload", {})
            drone_id = payload.get("drone_id")
            if not drone_id:
                return self._create_response(
                    message, "failed", error_code="INVALID_REQUEST", reason="drone_id required"
                )

            # Регистрация посадки
            self.drone_registry.register_landing(drone_id)

            # Запуск диагностики и зарядки (внутренняя логика)
            diagnostics_ok = self._run_post_landing_diagnostics(drone_id)
            charging_started = self._auto_start_charging_if_needed(drone_id)

            status = "docked"
            return self._create_response(message, status)
        except Exception as e:
            logger.error(f"Error in dock: {e}")
            return self._create_response(
                message, "failed", error_code="PORT_DOCK_FAILED", reason=str(e)
            )

    def _handle_emergency_receive(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработка аварийного приёма."""
        return self._create_response(message, "emergency_ack")

    def _handle_health_check(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Проверка доступности сервиса."""
        try:
            # Простая проверка: попытка подключиться к Redis
            if hasattr(self, 'state_store') and self.state_store.redis.ping():
                return self._create_response(message, "health.ok")
            else:
                return self._create_response(message, "health.degraded", error_code="PORT_UNAVAILABLE")
        except Exception:
            return self._create_response(message, "health.degraded", error_code="PORT_UNAVAILABLE")

    # ==================== Внутренняя логика ====================

    def _run_post_landing_diagnostics(self, drone_id: str) -> bool:
        """Выполняет диагностику после посадки (имитация)."""
        logger.info(f"Running post-landing diagnostics for {drone_id}")
        # TODO: реальная диагностика (чтение сенсоров и т.п.)
        return True

    def _auto_start_charging_if_needed(self, drone_id: str) -> bool:
        """Автоматически запускает зарядку, если уровень батареи < 80%."""
        drone = self.drone_registry.get_drone(drone_id)
        if drone and float(drone.get("battery_level", 0)) < 80.0:
            self.battery_charger.charge_to_threshold(drone_id, 90.0)
            logger.info(f"Auto-started charging for {drone_id}")
            return True
        return False

    def get_status(self) -> Dict[str, Any]:
        """Расширенный статус системы для healthcheck."""
        status = super().get_status()
        status.update({
            "name": self.name,
            "component_mode": StateStore is not None,
        })
        if hasattr(self, 'state_store'):
            try:
                status["redis_connected"] = self.state_store.redis.ping()
            except Exception:
                status["redis_connected"] = False
        return status