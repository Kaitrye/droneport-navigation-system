"""
DroneSimulator - симулятор дрона для тестирования дронопорта.

Самостоятельный компонент-заглушка, имитирующий поведение дрона:
- Состояние (батарея, позиция, статус)
- Взлет/посадка
- Движение
- Зарядка
- Интеграция с дронопортом

Не зависит от других файлов проекта - работает самостоятельно.
"""
from typing import Dict, Any, Optional
from enum import Enum
import time


class DroneStatus(Enum):
    #Статусы дрона.
    IDLE = "idle"  # Ожидание
    TAKING_OFF = "taking_off"  # Взлет
    FLYING = "flying"  # В полете
    LANDING = "landing"  # Посадка
    LANDED = "landed"  # Приземлен
    CHARGING = "charging"  # Зарядка
    MAINTENANCE = "maintenance"  # Обслуживание
    ERROR = "error"  # Ошибка


class DroneSimulator:
    """
    Симулятор дрона для тестирования дронопорта.
    
    Самостоятельный класс-заглушка, имитирующий поведение дрона.
    Не зависит от других компонентов проекта.
    """

    def __init__(
        self,
        drone_id: str,
        name: str = None,
        initial_battery: float = 100.0,
        initial_position: Optional[Dict[str, float]] = None,
    ):
        """
        Инициализация симулятора дрона.
        
        Args:
            drone_id: Уникальный ID дрона
            name: Имя дрона (опционально)
            initial_battery: Начальный уровень батареи (0-100)
            initial_position: Начальная позиция {"x": 0.0, "y": 0.0, "z": 0.0}
        """
        self.drone_id = drone_id
        self.name = name or f"Drone {drone_id}"
        self._initial_battery = max(0.0, min(100.0, initial_battery))
        
        # Состояние дрона
        self._state = {
            "status": DroneStatus.IDLE.value,
            "battery": self._initial_battery,
            "position": initial_position or {"x": 0.0, "y": 0.0, "z": 0.0},
            "altitude": 0.0,
            "speed": 0.0,
            "last_update": time.time(),
            "flight_time": 0.0,  # Время в полете (секунды)
            "total_flights": 0,
            "is_at_droneport": True,  # Находится ли дрон в дронопорте
            "droneport_id": None,  # ID дронопорта, где находится дрон
        }
        
        print(f"DroneSimulator '{self.name}' (ID: {drone_id}) initialized")
        print(f"  Initial battery: {self._initial_battery}%")
        print(f"  Initial position: {self._state['position']}")

    def takeoff(self, altitude: float = 10.0) -> Dict[str, Any]:
        """
        Симулирует взлет дрона.
        
        Args:
            altitude: Высота взлета (метры, по умолчанию 10.0)
        
        Returns:
            Dict с результатом операции
        """
        current_status = self._state["status"]
        
        # Проверка возможности взлета
        if current_status not in [DroneStatus.IDLE.value, DroneStatus.LANDED.value]:
            return {
                "success": False,
                "error": f"Cannot takeoff from status: {current_status}",
                "current_status": current_status,
            }
        
        if self._state["battery"] < 20.0:
            return {
                "success": False,
                "error": "Battery too low for takeoff (minimum 20%)",
                "battery": self._state["battery"],
            }
        
        # Взлет
        self._state["status"] = DroneStatus.TAKING_OFF.value
        self._state["altitude"] = 0.0
        self._state["speed"] = 0.0
        self._state["is_at_droneport"] = False
        
        # Симуляция взлета (в реальности это занимает время)
        time.sleep(0.1)  # Небольшая задержка для симуляции
        
        self._state["status"] = DroneStatus.FLYING.value
        self._state["altitude"] = altitude
        self._state["position"]["z"] = altitude
        self._state["last_update"] = time.time()
        self._state["total_flights"] += 1
        
        return {
            "success": True,
            "status": self._state["status"],
            "altitude": self._state["altitude"],
            "position": self._state["position"],
            "battery": self._state["battery"],
        }

    def land(self, position: Optional[Dict[str, float]] = None, droneport_id: Optional[str] = None) -> Dict[str, Any]:
        """
        Симулирует посадку дрона.
        
        Args:
            position: Позиция посадки {"x": float, "y": float} (опционально)
            droneport_id: ID дронопорта (опционально)
        
        Returns:
            Dict с результатом операции
        """
        current_status = self._state["status"]
        
        # Проверка возможности посадки
        if current_status not in [DroneStatus.FLYING.value, DroneStatus.TAKING_OFF.value]:
            return {
                "success": False,
                "error": f"Cannot land from status: {current_status}",
                "current_status": current_status,
            }
        
        # Посадка
        self._state["status"] = DroneStatus.LANDING.value
        
        # Симуляция посадки
        time.sleep(0.1)  # Небольшая задержка для симуляции
        
        if position:
            self._state["position"]["x"] = position.get("x", self._state["position"]["x"])
            self._state["position"]["y"] = position.get("y", self._state["position"]["y"])
        
        self._state["status"] = DroneStatus.LANDED.value
        self._state["altitude"] = 0.0
        self._state["position"]["z"] = 0.0
        self._state["speed"] = 0.0
        self._state["is_at_droneport"] = droneport_id is not None
        self._state["droneport_id"] = droneport_id
        self._state["last_update"] = time.time()
        
        return {
            "success": True,
            "status": self._state["status"],
            "position": self._state["position"],
            "battery": self._state["battery"],
            "droneport_id": droneport_id,
        }

    def move(self, target_position: Dict[str, float], speed: float = 5.0) -> Dict[str, Any]:
        """
        Симулирует движение дрона.
        
        Args:
            target_position: Целевая позиция {"x": float, "y": float, "z": float}
            speed: Скорость движения (м/с, по умолчанию 5.0)
        
        Returns:
            Dict с результатом операции
        """
        current_status = self._state["status"]
        
        # Проверка возможности движения
        if current_status != DroneStatus.FLYING.value:
            return {
                "success": False,
                "error": f"Cannot move from status: {current_status}",
                "current_status": current_status,
            }
        
        if not target_position:
            return {
                "success": False,
                "error": "target_position is required",
            }
        
        # Симуляция движения
        old_position = self._state["position"].copy()
        self._state["position"]["x"] = target_position.get("x", self._state["position"]["x"])
        self._state["position"]["y"] = target_position.get("y", self._state["position"]["y"])
        self._state["position"]["z"] = target_position.get("z", self._state["position"]["z"])
        self._state["altitude"] = self._state["position"]["z"]
        self._state["speed"] = speed
        self._state["last_update"] = time.time()
        
        # Потребление батареи при движении
        distance = (
            (self._state["position"]["x"] - old_position["x"]) ** 2 +
            (self._state["position"]["y"] - old_position["y"]) ** 2 +
            (self._state["position"]["z"] - old_position["z"]) ** 2
        ) ** 0.5
        battery_consumption = distance * 0.1  # Примерное потребление
        self._update_battery(battery_consumption)
        
        return {
            "success": True,
            "position": self._state["position"],
            "battery": self._state["battery"],
            "speed": self._state["speed"],
        }

    def charge(self, target_level: float = 100.0) -> Dict[str, Any]:
        """
        Симулирует зарядку дрона.
        
        Args:
            target_level: Целевой уровень батареи (0-100, по умолчанию 100)
        
        Returns:
            Dict с результатом операции
        """
        target_level = max(0.0, min(100.0, target_level))
        current_status = self._state["status"]
        
        # Проверка возможности зарядки
        if current_status not in [DroneStatus.LANDED.value, DroneStatus.IDLE.value]:
            return {
                "success": False,
                "error": f"Cannot charge from status: {current_status}",
                "current_status": current_status,
            }
        
        if not self._state["is_at_droneport"]:
            return {
                "success": False,
                "error": "Drone must be at droneport to charge",
                "is_at_droneport": self._state["is_at_droneport"],
            }
        
        # Зарядка
        old_status = self._state["status"]
        self._state["status"] = DroneStatus.CHARGING.value
        
        # Симуляция зарядки (в реальности это занимает время)
        while self._state["battery"] < target_level:
            self._update_battery()
            time.sleep(0.05)  # Небольшая задержка для симуляции
        
        self._state["battery"] = target_level
        self._state["status"] = old_status  # Возвращаем предыдущий статус
        self._state["last_update"] = time.time()
        
        return {
            "success": True,
            "battery": self._state["battery"],
            "status": self._state["status"],
        }

    def get_state(self) -> Dict[str, Any]:
        """
        Возвращает текущее состояние дрона.
        
        Returns:
            Dict с текущим состоянием дрона
        """
        # Обновляем батарею в зависимости от статуса
        if self._state["status"] == DroneStatus.FLYING.value:
            # В полете батарея постепенно уменьшается
            time_passed = time.time() - self._state["last_update"]
            if time_passed > 0:
                self._update_battery(time_passed * 0.1)  # Примерное потребление
                self._state["last_update"] = time.time()
        
        return {
            **self._state,
            "drone_id": self.drone_id,
            "name": self.name,
        }

    def _update_battery(self, consumption: float = 0.0):
        """
        Обновление уровня батареи.
        
        Args:
            consumption: Потребление батареи (положительное значение уменьшает заряд)
        """
        if self._state["status"] == DroneStatus.CHARGING.value:
            # При зарядке батарея увеличивается
            self._state["battery"] = min(100.0, self._state["battery"] + 1.0)
        elif self._state["status"] in [DroneStatus.FLYING.value, DroneStatus.TAKING_OFF.value]:
            # В полете батарея уменьшается
            self._state["battery"] = max(0.0, self._state["battery"] - consumption)
            if self._state["battery"] <= 0:
                self._state["status"] = DroneStatus.ERROR.value
                self._state["battery"] = 0.0
