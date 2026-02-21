"""
E2E тесты DummySystem через реальный брокер.
Требует: make docker-up (kafka/mosquitto + dummy_system_a + dummy_system_b).
Параметры: docker/.env (BROKER_TYPE, BROKER_HOST, KAFKA_PORT, MQTT_PORT, ADMIN_USER, ADMIN_PASSWORD).
"""
import pytest
import os
import time
import socket


def _broker_available(retries=5, delay=2):
    """Проверка доступности брокера (с повторами после docker-up)."""
    bt = os.environ.get("BROKER_TYPE", "kafka").lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    port_val = os.environ.get("MQTT_PORT", "1883") if bt == "mqtt" else os.environ.get("KAFKA_PORT", "9092")
    port = int(port_val) if isinstance(port_val, str) else int(port_val)
    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(delay)
    return False


@pytest.fixture(scope="module")
def system_bus():
    """SystemBus (реальный брокер). Пропуск, если брокер недоступен."""
    if not _broker_available():
        pytest.skip(
            f"Broker ({os.environ.get('BROKER_TYPE', 'kafka')}) at {os.environ.get('BROKER_HOST', 'localhost')} not available. Run: make docker-up"
        )
    from broker.bus_factory import create_system_bus

    bt = os.environ.get("BROKER_TYPE", "kafka").lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    kafka_port = os.environ.get("KAFKA_PORT", "9092")
    mqtt_port = os.environ.get("MQTT_PORT", "1883")
    # Тестовый клиент подключается с учётными данными admin (Kafka SASL / MQTT)
    if not os.environ.get("BROKER_USER") and os.environ.get("ADMIN_USER"):
        os.environ["BROKER_USER"] = os.environ["ADMIN_USER"]
    if not os.environ.get("BROKER_PASSWORD") and os.environ.get("ADMIN_PASSWORD"):
        os.environ["BROKER_PASSWORD"] = os.environ["ADMIN_PASSWORD"]
    if bt == "kafka":
        os.environ["BROKER_TYPE"] = "kafka"
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = os.environ.get("KAFKA_BOOTSTRAP_SERVERS", f"{host}:{kafka_port}")
    else:
        os.environ["BROKER_TYPE"] = "mqtt"
        os.environ["MQTT_BROKER"] = os.environ.get("MQTT_BROKER", host)
        os.environ["MQTT_PORT"] = str(mqtt_port)

    bus = create_system_bus(client_id="test_client")
    bus.start()
    time.sleep(2)

    yield bus

    bus.stop()


class TestDummySystemE2E:
    """E2E: клиент шлёт запросы в DummySystem (контейнеры dummy_system_a, dummy_system_b)."""

    def test_echo(self, system_bus):
        """Echo: один из контейнеров возвращает данные."""
        from shared.topics import SystemTopics, DummyActions

        response = system_bus.request(
            SystemTopics.DUMMY,
            {
                "action": DummyActions.ECHO,
                "sender": "test_client",
                "payload": {"data": "hello"},
            },
            timeout=10.0,
        )

        assert response is not None
        assert response.get("success") is True
        assert response["payload"]["echo"] == "hello"
        assert "from" in response["payload"]

    def test_process(self, system_bus):
        """Process: один из контейнеров обрабатывает value * 2."""
        from shared.topics import SystemTopics, DummyActions

        response = system_bus.request(
            SystemTopics.DUMMY,
            {
                "action": DummyActions.PROCESS,
                "sender": "test_client",
                "payload": {"value": 21},
            },
            timeout=10.0,
        )

        assert response is not None
        assert response.get("success") is True
        assert response["payload"]["result"] == 42
        assert "processed_by" in response["payload"]
