"""
DummySystem - шаблон для создания новых систем.

Копируй эту папку и адаптируй под свои нужды.
"""
from typing import Dict, Any, Optional

from shared.base_system import BaseSystem
from shared.topics import SystemTopics, DummyActions
from broker.system_bus import SystemBus


class DummySystem(BaseSystem):
    """
    Пример системы. Используй как шаблон.
    
    Для создания своей системы:
    1. Скопируй эту папку
    2. Переименуй класс
    3. Добавь свои handlers
    """

    def __init__(
        self,
        system_id: str,
        name: str,
        bus: SystemBus,
        health_port: Optional[int] = None
    ):
        super().__init__(
            system_id=system_id,
            system_type="dummy",
            topic=SystemTopics.DUMMY,  # Топик из shared/topics.py
            bus=bus,
            health_port=health_port
        )
        self.name = name
        print(f"DummySystem '{name}' initialized")

    def _register_handlers(self):
        """Регистрация обработчиков для каждого action."""
        # Формат: self.register_handler(ACTION, handler_method)
        self.register_handler(DummyActions.ECHO, self._handle_echo)
        self.register_handler(DummyActions.PROCESS, self._handle_process)

    # =========================================================================
    # Handlers - обработчики входящих сообщений
    # =========================================================================

    def _handle_echo(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработчик action=echo.
        Возвращает полученные данные обратно.
        
        Входящий payload:
            data: Any - данные для эха
            
        Возвращает:
            echo: Any - те же данные
        """
        payload = message.get("payload", {})
        data = payload.get("data")
        
        return {"echo": data, "from": self.system_id}

    def _handle_process(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """
        Обработчик action=process.
        Пример обработки данных.
        
        Входящий payload:
            value: int - число для обработки
            
        Возвращает:
            result: int - обработанное значение
        """
        payload = message.get("payload", {})
        value = payload.get("value", 0)
        
        # Твоя логика здесь
        result = value * 2
        
        return {"result": result, "processed_by": self.system_id}

    # =========================================================================
    # Отправка сообщений в другие системы
    # =========================================================================

    def send_to_other_system(self, target_topic: str, action: str, payload: dict) -> Optional[dict]:
        """
        Пример отправки запроса в другую систему.
        
        Args:
            target_topic: Топик целевой системы (например SystemTopics.DUMMY)
            action: Действие (например FleetActions.GET_ALL_DRONES)
            payload: Данные запроса
            
        Returns:
            Ответ от системы или None при таймауте
        """
        response = self.bus.request(
            target_topic,
            {
                "action": action,
                "sender": self.system_id,
                "payload": payload
            },
            timeout=10.0
        )
        return response

    def publish_event(self, target_topic: str, action: str, payload: dict) -> bool:
        """
        Отправка события без ожидания ответа (fire-and-forget).
        
        Args:
            target_topic: Топик
            action: Действие
            payload: Данные
            
        Returns:
            True если отправлено успешно
        """
        return self.bus.publish(
            target_topic,
            {
                "action": action,
                "sender": self.system_id,
                "payload": payload
            }
        )

    def get_status(self) -> Dict[str, Any]:
        """Расширенный статус системы."""
        status = super().get_status()
        status.update({
            "name": self.name,
            "custom_metric": 42
        })
        return status
