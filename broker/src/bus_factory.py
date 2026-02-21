"""
Factory для создания EventBus и SystemBus на основе конфигурации.
Поддерживаемые типы: kafka, mqtt.
"""
import os
from typing import Dict, Optional, TYPE_CHECKING

from broker.kafka.kafka_bus import KafkaEventBus
from broker.mqtt.mqtt_bus import MQTTEventBus
from .system_bus import SystemBus
from broker.kafka.kafka_system_bus import KafkaSystemBus
from broker.mqtt.mqtt_system_bus import MQTTSystemBus

if TYPE_CHECKING:
    from broker import EventBus


def create_event_bus(
    bus_type: Optional[str] = None, config: Optional[Dict] = None
) -> "EventBus":
    """
    Создает EventBus указанного типа.
    
    Args:
        bus_type: Тип EventBus ("kafka", "mqtt").
                  Если None, берется из config или EVENT_BUS_TYPE.
        config: Словарь с конфигурацией.
    """
    if bus_type is None:
        if config and "event_bus" in config and "type" in config["event_bus"]:
            bus_type = config["event_bus"]["type"]
        else:
            bus_type = os.getenv("EVENT_BUS_TYPE", "mqtt")
    
    bus_type = bus_type.lower()
    
    kafka_config = {}
    mqtt_config = {}
    
    if config and "event_bus" in config:
        kafka_config = config["event_bus"].get("kafka", {})
        mqtt_config = config["event_bus"].get("mqtt", {})
    
    if bus_type == "kafka":
        bootstrap_servers = kafka_config.get(
            "bootstrap_servers", os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        )
        client_id = kafka_config.get(
            "client_id", os.getenv("KAFKA_CLIENT_ID", "drone_event_bus")
        )
        return KafkaEventBus(bootstrap_servers=bootstrap_servers, client_id=client_id)
    
    elif bus_type == "mqtt":
        broker = mqtt_config.get("broker", os.getenv("MQTT_BROKER", "localhost"))
        port = mqtt_config.get("port", int(os.getenv("MQTT_PORT", "1883")))
        client_id = mqtt_config.get(
            "client_id", os.getenv("MQTT_CLIENT_ID", "drone_event_bus")
        )
        qos = mqtt_config.get("qos", int(os.getenv("MQTT_QOS", "1")))
        return MQTTEventBus(broker=broker, port=port, client_id=client_id, qos=qos)
    
    else:
        raise ValueError(
            f"Unknown bus type: {bus_type}. Supported types: 'kafka', 'mqtt'"
        )


def create_system_bus(
    bus_type: Optional[str] = None, 
    client_id: Optional[str] = None,
    config: Optional[Dict] = None
) -> SystemBus:
    """
    Создает SystemBus указанного типа для межсистемного взаимодействия.
    
    Args:
        bus_type: Тип SystemBus ("kafka", "mqtt").
                  Если None, берется из переменной окружения BROKER_TYPE.
        client_id: Идентификатор клиента (для Kafka/MQTT)
        config: Словарь с конфигурацией:
                - broker.type: тип брокера
                - broker.kafka: настройки Kafka
                - broker.mqtt: настройки MQTT
    
    Returns:
        SystemBus: Экземпляр SystemBus указанного типа
        
    Raises:
        ValueError: Если указан неизвестный тип
        ImportError: Если требуемые библиотеки не установлены
    """
    # Определяем тип брокера
    if bus_type is None:
        if config and "broker" in config and "type" in config["broker"]:
            bus_type = config["broker"]["type"]
        else:
            bus_type = os.getenv("BROKER_TYPE", "kafka")
    
    bus_type = bus_type.lower()
    
    # Извлекаем конфигурацию
    kafka_config = {}
    mqtt_config = {}
    
    if config and "broker" in config:
        kafka_config = config["broker"].get("kafka", {})
        mqtt_config = config["broker"].get("mqtt", {})
    
    # Создаем SystemBus
    if bus_type == "kafka":
        bootstrap_servers = kafka_config.get(
            "bootstrap_servers", 
            os.getenv("KAFKA_BOOTSTRAP_SERVERS", "localhost:9092")
        )
        cid = client_id or kafka_config.get(
            "client_id", 
            os.getenv("SYSTEM_ID", "system_bus")
        )
        group_id = kafka_config.get(
            "group_id",
            os.getenv("KAFKA_GROUP_ID")
        )
        return KafkaSystemBus(
            bootstrap_servers=bootstrap_servers, 
            client_id=cid,
            group_id=group_id
        )
    
    elif bus_type == "mqtt":
        broker = mqtt_config.get("broker", os.getenv("MQTT_BROKER", "localhost"))
        port = mqtt_config.get("port", int(os.getenv("MQTT_PORT", "1883")))
        cid = client_id or mqtt_config.get(
            "client_id", 
            os.getenv("SYSTEM_ID", "system_bus")
        )
        qos = mqtt_config.get("qos", int(os.getenv("MQTT_QOS", "1")))
        return MQTTSystemBus(broker=broker, port=port, client_id=cid, qos=qos)
    
    else:
        raise ValueError(
            f"Unknown broker type: {bus_type}. Supported types: 'kafka', 'mqtt'"
        )
