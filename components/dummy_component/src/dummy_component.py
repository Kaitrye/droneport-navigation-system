"""
DummyComponent - шаблон для создания новых компонентов дрона.

Копируй эту папку и адаптируй под свои нужды.
"""
from broker import EventBus
from shared.event import Event


class DummyComponent:
    """
    Шаблон компонента дрона.
    
    Компонент:
    - Подписывается на события через EventBus
    - Обрабатывает входящие события
    - Отправляет ответы в destination
    """

    def __init__(self, event_bus: EventBus):
        """
        Args:
            event_bus: Шина событий дрона
        """
        self.event_bus = event_bus
        
        # Подписка на события для этого компонента
        self.event_bus.subscribe("dummy_component", self._handle_event)
        
        # Внутреннее состояние
        self._state = {"counter": 0}

    def _handle_event(self, event: Event):
        """
        Обработчик входящих событий.
        Маршрутизация по event.operation.
        """
        if event.operation == "echo":
            self._handle_echo(event)
        elif event.operation == "increment":
            self._handle_increment(event)
        elif event.operation == "get_state":
            self._handle_get_state(event)
        else:
            print(f"dummy_component: Unknown operation: {event.operation}")

    def _handle_echo(self, event: Event):
        """Возвращает полученные данные обратно."""
        response = Event(
            source="dummy_component",
            destination=event.source,
            operation="echo_response",
            parameters=event.parameters
        )
        self.event_bus.publish(response, response.destination)

    def _handle_increment(self, event: Event):
        """Увеличивает счётчик."""
        self._state["counter"] += event.parameters.get("value", 1)
        
        response = Event(
            source="dummy_component",
            destination=event.source,
            operation="increment_response",
            parameters={"counter": self._state["counter"]}
        )
        self.event_bus.publish(response, response.destination)

    def _handle_get_state(self, event: Event):
        """Возвращает текущее состояние."""
        response = Event(
            source="dummy_component",
            destination=event.source,
            operation="state_response",
            parameters=self._state.copy()
        )
        self.event_bus.publish(response, response.destination)

    # =========================================================================
    # Отправка событий другим компонентам
    # =========================================================================

    def send_to_component(self, destination: str, operation: str, params: dict):
        """
        Отправка события другому компоненту.
        
        Args:
            destination: Компонент-получатель (telemetry, communication, etc.)
            operation: Операция
            params: Параметры
        """
        event = Event(
            source="dummy_component",
            destination=destination,
            operation=operation,
            parameters=params
        )
        self.event_bus.publish(event, destination)
