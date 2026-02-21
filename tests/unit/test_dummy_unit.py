"""
Unit тесты для DummyComponent и DummySystem.
Без внешних зависимостей (Docker, брокеры).
"""
import pytest
from unittest.mock import MagicMock, patch


class TestDummyComponent:
    """Unit тесты DummyComponent."""

    def test_increment(self):
        """Тест increment: увеличение счётчика."""
        from components.dummy_component.src.dummy_component import DummyComponent
        from shared.event import Event

        bus = MagicMock()
        component = DummyComponent(bus)

        assert component._state["counter"] == 0

        event = Event(
            source="test",
            destination="dummy_component",
            operation="increment",
            parameters={"value": 5}
        )
        component._handle_event(event)

        assert component._state["counter"] == 5

    def test_echo(self):
        """Тест echo: возврат данных."""
        from components.dummy_component.src.dummy_component import DummyComponent
        from shared.event import Event

        bus = MagicMock()
        bus.publish = MagicMock(return_value=True)

        component = DummyComponent(bus)

        event = Event(
            source="test_sender",
            destination="dummy_component",
            operation="echo",
            parameters={"message": "hello"}
        )
        component._handle_event(event)

        assert bus.publish.called
        call_args = bus.publish.call_args
        response_event = call_args[0][0]
        assert response_event.operation == "echo_response"
        assert response_event.parameters == {"message": "hello"}


class TestDummySystem:
    """Unit тесты DummySystem."""

    def test_handle_echo(self):
        """Тест echo handler."""
        from systems.dummy_system.src.dummy import DummySystem

        # Mock SystemBus
        mock_bus = MagicMock()
        mock_bus.subscribe = MagicMock()
        mock_bus.start = MagicMock()

        with patch('shared.base_system.threading'):
            system = DummySystem(
                system_id="test_dummy",
                name="TestDummy",
                bus=mock_bus,
                health_port=None
            )

        message = {
            "action": "echo",
            "sender": "test_client",
            "payload": {"data": "test_data"}
        }

        result = system._handle_echo(message)

        assert result["echo"] == "test_data"
        assert result["from"] == "test_dummy"

    def test_handle_process(self):
        """Тест process handler: value * 2."""
        from systems.dummy_system.src.dummy import DummySystem

        mock_bus = MagicMock()
        mock_bus.subscribe = MagicMock()
        mock_bus.start = MagicMock()

        with patch('shared.base_system.threading'):
            system = DummySystem(
                system_id="test_dummy",
                name="TestDummy",
                bus=mock_bus,
                health_port=None
            )

        message = {
            "action": "process",
            "sender": "test_client",
            "payload": {"value": 21}
        }

        result = system._handle_process(message)

        assert result["result"] == 42
        assert result["processed_by"] == "test_dummy"
