"""Тесты для DummyComponent."""
import pytest
from pytest_mock import MockerFixture

from dummy_component import DummyComponent
from shared.event import Event


@pytest.fixture
def event_bus(mocker: MockerFixture):
    return mocker.patch('broker.EventBus')



@pytest.fixture
def component(event_bus):
    return DummyComponent(event_bus)



def test_subscribe_on_init(mocker: MockerFixture, event_bus, component):
    """Компонент подписывается на события при инициализации."""
    # Проверяем, что subscribe был вызван ровно один раз
    assert event_bus.subscribe.call_count == 1

    # Проверяем аргументы вызова subscribe
    call_args = event_bus.subscribe.call_args[0]
    assert call_args[0] == "dummy_component"
    assert call_args[1] == component._handle_event



def test_echo(mocker: MockerFixture, event_bus, component):
    """Echo возвращает те же данные."""
    event = Event(
        source="test",
        destination="dummy_component",
        operation="echo",
        parameters={"data": "test_data"}
    )
    component._handle_event(event)

    # Проверяем, что publish был вызван один раз
    assert event_bus.publish.call_count == 1

    # Получаем аргументы вызова publish
    call_args = event_bus.publish.call_args[0]
    response = call_args[0]  # Первый аргумент вызова

    assert response.operation == "echo_response"
    assert response.parameters == {"data": "test_data"}



def test_increment(mocker: MockerFixture, event_bus, component):
    """Increment увеличивает счётчик."""
    event = Event(
        source="test",
        destination="dummy_component",
        operation="increment",
        parameters={"value": 5}
    )
    component._handle_event(event)

    assert component._state["counter"] == 5
