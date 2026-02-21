"""
Broker module - шины для передачи событий и сообщений.

Структура:
- broker/           - EventBus base class
- broker/src/       - SystemBus, factories
- broker/kafka/     - KafkaEventBus, KafkaSystemBus
- broker/mqtt/      - MQTTEventBus, MQTTSystemBus
"""
from abc import ABC, abstractmethod
from typing import Callable, List

from shared.event import Event


class EventBus(ABC):
    """
    Абстрактный базовый класс для системы передачи событий между модулями.
    
    Все реализации EventBus должны наследоваться от этого класса
    и реализовывать все абстрактные методы.
    """

    @abstractmethod
    def publish(self, event: Event, destination: str) -> bool:
        """
        Отправляет событие указанному модулю-получателю.
        
        Args:
            event: Событие для отправки
            destination: Имя модуля-получателя
            
        Returns:
            bool: True если событие успешно отправлено
        """
        pass

    @abstractmethod
    def subscribe(
        self, module_name: str, callback: Callable[[Event], None]
    ) -> bool:
        """
        Подписывает модуль на получение событий.
        
        Args:
            module_name: Имя модуля-подписчика
            callback: Функция-обработчик, вызываемая при получении события
            
        Returns:
            bool: True если подписка успешно создана
        """
        pass

    @abstractmethod
    def unsubscribe(self, module_name: str) -> bool:
        """
        Отписывает модуль от получения событий.
        
        Args:
            module_name: Имя модуля для отписки
            
        Returns:
            bool: True если отписка успешна
        """
        pass

    @abstractmethod
    def get_events_for_module(self, module_name: str) -> List[Event]:
        """
        Получает все накопленные события для указанного модуля (pull-модель).
        
        Args:
            module_name: Имя модуля
            
        Returns:
            List[Event]: Список событий для модуля
        """
        pass
