# Components

Компоненты - модули дрона, взаимодействующие через EventBus.

Шаблон: `dummy_component/`

## Структура

```
components/my_component/
├── src/
│   ├── __init__.py
│   └── my_component.py
└── tests/
    └── test_my_component.py
```

## Класс компонента

```python
from broker import EventBus
from shared.event import Event

class MyComponent:
    def __init__(self, event_bus: EventBus):
        self.event_bus = event_bus
        self.event_bus.subscribe("my_component", self._handle_event)

    def _handle_event(self, event: Event):
        if event.operation == "do_action":
            response = Event(
                source="my_component",
                destination=event.source,
                operation="action_result",
                parameters={"result": "ok"}
            )
            self.event_bus.publish(response, event.source)
```

## EventBus API

```python
self.event_bus.subscribe("my_component", self._handle_event)
self.event_bus.publish(event, destination)
```
