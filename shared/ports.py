"""
Конфигурация портов и хостов для систем drones_v2.

Поддерживает переменные окружения для Docker-развертывания.
В Docker хосты = имена контейнеров, локально = localhost.
"""
import os

# =============================================================================
# Порты систем
# =============================================================================

FLEET_PORT = int(os.environ.get("FLEET_PORT", "6000"))
INSURANCE_PORT = int(os.environ.get("INSURANCE_PORT", "7000"))
CERTIFICATION_PORT = int(os.environ.get("CERTIFICATION_PORT", "8000"))
AGGREGATOR_PORT = int(os.environ.get("AGGREGATOR_PORT", "9000"))
ORCHESTRATOR_PORT = int(os.environ.get("ORCHESTRATOR_PORT", "9600"))
DUMMY_PORT = int(os.environ.get("DUMMY_PORT", "9700"))

# Kafka
KAFKA_PORT = int(os.environ.get("KAFKA_PORT", "9092"))

# MQTT
MQTT_PORT = int(os.environ.get("MQTT_PORT", "1883"))

# Компоненты дрона (базовый порт, каждый дрон получает уникальный)
COMMUNICATION_BASE_PORT = int(os.environ.get("COMMUNICATION_BASE_PORT", "5000"))


# =============================================================================
# Хосты систем (для Docker используем имена контейнеров)
# =============================================================================

FLEET_HOST = os.environ.get("FLEET_HOST", "localhost")
INSURANCE_HOST = os.environ.get("INSURANCE_HOST", "localhost")
CERTIFICATION_HOST = os.environ.get("CERTIFICATION_HOST", "localhost")
AGGREGATOR_HOST = os.environ.get("AGGREGATOR_HOST", "localhost")
ORCHESTRATOR_HOST = os.environ.get("ORCHESTRATOR_HOST", "localhost")
KAFKA_HOST = os.environ.get("KAFKA_HOST", "localhost")
MQTT_HOST = os.environ.get("MQTT_HOST", os.environ.get("MQTT_BROKER", "localhost"))


# =============================================================================
# Функции для получения URL сервисов
# =============================================================================

def get_fleet_url() -> str:
    """Возвращает URL для Fleet сервиса."""
    return f"http://{FLEET_HOST}:{FLEET_PORT}"


def get_insurance_url() -> str:
    """Возвращает URL для Insurance сервиса."""
    return f"http://{INSURANCE_HOST}:{INSURANCE_PORT}"


def get_certification_url() -> str:
    """Возвращает URL для Certification сервиса."""
    return f"http://{CERTIFICATION_HOST}:{CERTIFICATION_PORT}"


def get_aggregator_url() -> str:
    """Возвращает URL для Aggregator сервиса."""
    return f"http://{AGGREGATOR_HOST}:{AGGREGATOR_PORT}"


def get_orchestrator_url() -> str:
    """Возвращает URL для DroneOrchestrator сервиса."""
    return f"http://{ORCHESTRATOR_HOST}:{ORCHESTRATOR_PORT}"


def get_kafka_bootstrap() -> str:
    """Возвращает bootstrap servers для Kafka."""
    return f"{KAFKA_HOST}:{KAFKA_PORT}"


def get_mqtt_broker() -> tuple[str, int]:
    """Возвращает (host, port) для MQTT брокера."""
    return MQTT_HOST, MQTT_PORT
