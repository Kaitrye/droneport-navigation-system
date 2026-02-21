"""
Интеграционный тест: DummyComponent и брокер (Kafka/MQTT).
Параметры: docker/.env (BROKER_TYPE, BROKER_HOST, KAFKA_PORT, MQTT_PORT).
"""
import os
import time
import socket
import pytest


def _broker_available(retries=5, delay=2):
    """Проверка доступности брокера (с повторами после docker-up)."""
    bt = os.environ.get("BROKER_TYPE", "kafka").lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    port_val = (
        os.environ.get("MQTT_PORT", "1883")
        if bt == "mqtt"
        else os.environ.get("KAFKA_PORT", "9092")
    )
    port = int(port_val) if isinstance(port_val, str) else int(port_val)
    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(delay)
    return False


@pytest.fixture(scope="module")
def event_bus():
    """EventBus (реальный брокер). Пропуск, если брокер недоступен."""
    if not _broker_available():
        pytest.skip(
            f"Broker ({os.environ.get('BROKER_TYPE', 'kafka')}) at "
            f"{os.environ.get('BROKER_HOST', 'localhost')} not available. Run: make docker-up"
        )
    from broker.bus_factory import create_event_bus

    bt = os.environ.get("BROKER_TYPE", "kafka").lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    kafka_port = os.environ.get("KAFKA_PORT", "9092")
    mqtt_port = os.environ.get("MQTT_PORT", "1883")

    if not os.environ.get("BROKER_USER") and os.environ.get("ADMIN_USER"):
        os.environ["BROKER_USER"] = os.environ["ADMIN_USER"]
    if not os.environ.get("BROKER_PASSWORD") and os.environ.get("ADMIN_PASSWORD"):
        os.environ["BROKER_PASSWORD"] = os.environ["ADMIN_PASSWORD"]

    os.environ["EVENT_BUS_TYPE"] = bt
    cid = "test_dummy_component_integration"
    if bt == "kafka":
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", f"{host}:{kafka_port}"
        )
        os.environ["KAFKA_CLIENT_ID"] = cid
    else:
        os.environ["MQTT_BROKER"] = os.environ.get("MQTT_BROKER", host)
        os.environ["MQTT_PORT"] = str(mqtt_port)
        os.environ["MQTT_CLIENT_ID"] = cid

    bus = create_event_bus()
    yield bus

    if hasattr(bus, "disconnect"):
        bus.disconnect()


class TestDummyComponentBrokerIntegration:
    """Интеграция: DummyComponent получает события через брокер и отвечает."""

    def test_echo_via_broker(self, event_bus):
        """Компонент получает echo через брокер и возвращает echo_response в тестовый топик."""
        from shared.event import Event
        from components.dummy_component.src.dummy_component import DummyComponent

        RESPONSE_TOPIC = "test_response_topic"
        responses = []

        def collect(event):
            responses.append(event)

        event_bus.subscribe(RESPONSE_TOPIC, collect)
        component = DummyComponent(event_bus)

        # Kafka consumers need time for partition assignment on new topics
        time.sleep(5)

        event_bus.publish(
            Event(
                source=RESPONSE_TOPIC,
                destination="dummy_component",
                operation="echo",
                parameters={"data": "hello_broker"},
            ),
            "dummy_component",
        )

        time.sleep(5)

        assert len(responses) >= 1
        echo_resp = next((r for r in responses if r.operation == "echo_response"), None)
        assert echo_resp is not None
        assert echo_resp.parameters == {"data": "hello_broker"}
        assert echo_resp.source == "dummy_component"
        assert echo_resp.destination == RESPONSE_TOPIC
