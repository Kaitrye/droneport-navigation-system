"""
MQTT реализация EventBus для передачи событий через MQTT broker (например, Mosquitto).
Требует запущенный MQTT broker.
"""
import json
import os
import threading
from typing import Callable, Dict, List

try:
    import paho.mqtt.client as mqtt
    MQTT_AVAILABLE = True
except ImportError:
    MQTT_AVAILABLE = False

from broker import EventBus
from shared.event import Event


class MQTTEventBus(EventBus):
    """
    Реализация EventBus на основе MQTT протокола.
    
    Каждый модуль использует свой топик: drones/{module_name}/events
    События сериализуются в JSON для передачи через MQTT.
    """

    def __init__(self, broker: str = "localhost", port: int = 1883, client_id: str = "drone_event_bus", qos: int = 1):
        """
        Инициализация MQTT EventBus.
        
        Args:
            broker: Адрес MQTT broker
            port: Порт MQTT broker
            client_id: Идентификатор клиента MQTT
            qos: Quality of Service level (0, 1, or 2)
        """
        if not MQTT_AVAILABLE:
            raise ImportError(
                "paho-mqtt is not installed. Install it with: pip install paho-mqtt"
            )

        self.broker = broker
        self.port = port
        self.client_id = client_id
        self.qos = qos
        
        self._client = mqtt.Client(client_id=client_id)
        self._client.on_connect = self._on_connect
        self._client.on_message = self._on_message
        
        username = os.environ.get("BROKER_USER")
        password = os.environ.get("BROKER_PASSWORD")
        if username and password:
            self._client.username_pw_set(username, password)
        
        self._callbacks: Dict[str, Callable[[Event], None]] = {}
        self._event_buffers: Dict[str, List[Event]] = {}
        self._buffer_lock = threading.Lock()
        
        try:
            self._client.connect(broker, port, 60)
            self._client.loop_start()  # Запускаем фоновый поток для обработки сообщений
        except Exception as e:
            raise ConnectionError(f"Failed to connect to MQTT broker at {broker}:{port}: {e}")

    def _on_connect(self, client, userdata, flags, rc, *args, **kwargs):
        """Callback при подключении к MQTT broker. Совместим с paho-mqtt 1.x и 2.x."""
        rc_value = rc if isinstance(rc, int) else getattr(rc, 'value', 0)
        if rc_value == 0:
            print(f"MQTT EventBus connected to broker {self.broker}:{self.port}")
        else:
            print(f"Failed to connect to MQTT broker, return code {rc}")

    def _on_message(self, client, userdata, msg):
        """Callback при получении сообщения из MQTT топика."""
        try:
            # Извлекаем имя модуля из топика: drones/{module_name}/events
            topic_parts = msg.topic.split('/')
            if len(topic_parts) >= 3 and topic_parts[0] == "drones" and topic_parts[2] == "events":
                module_name = topic_parts[1]
                
                # Десериализуем событие
                event_dict = json.loads(msg.payload.decode('utf-8'))
                event = Event.from_dict(event_dict)
                
                # Вызываем callback, если есть
                if module_name in self._callbacks:
                    self._callbacks[module_name](event)
                
                # Добавляем в буфер для pull-модели
                with self._buffer_lock:
                    if module_name not in self._event_buffers:
                        self._event_buffers[module_name] = []
                    self._event_buffers[module_name].append(event)
        except Exception as e:
            print(f"Error processing MQTT message: {e}")

    def _get_topic_name(self, module_name: str) -> str:
        """Формирует имя топика для модуля."""
        return f"drones/{module_name}/events"

    def publish(self, event: Event, destination: str) -> bool:
        """
        Отправляет событие в MQTT топик модуля-получателя.
        
        Args:
            event: Событие для отправки
            destination: Имя модуля-получателя
            
        Returns:
            bool: True если событие успешно отправлено
        """
        topic = self._get_topic_name(destination)
        event_dict = event.to_dict()
        payload = json.dumps(event_dict).encode('utf-8')
        
        try:
            result = self._client.publish(topic, payload, qos=self.qos)
            if result.rc == mqtt.MQTT_ERR_SUCCESS:
                return True
            else:
                print(f"Failed to publish event to MQTT topic {topic}, return code {result.rc}")
                return False
        except Exception as e:
            print(f"Error publishing event to MQTT topic {topic}: {e}")
            return False

    def subscribe(
        self, module_name: str, callback: Callable[[Event], None]
    ) -> bool:
        """
        Подписывает модуль на получение событий из MQTT топика.
        
        Args:
            module_name: Имя модуля-подписчика
            callback: Функция-обработчик события
            
        Returns:
            bool: True если подписка успешна
        """
        self._callbacks[module_name] = callback
        
        topic = self._get_topic_name(module_name)
        
        # Подписываемся на топик
        result, mid = self._client.subscribe(topic, qos=self.qos)
        if result == mqtt.MQTT_ERR_SUCCESS:
            # Инициализируем буфер для модуля
            with self._buffer_lock:
                if module_name not in self._event_buffers:
                    self._event_buffers[module_name] = []
            return True
        else:
            print(f"Failed to subscribe to MQTT topic {topic}, return code {result}")
            return False

    def unsubscribe(self, module_name: str) -> bool:
        """
        Отписывает модуль от получения событий.
        
        Args:
            module_name: Имя модуля
            
        Returns:
            bool: True если отписка успешна
        """
        if module_name in self._callbacks:
            del self._callbacks[module_name]
        
        topic = self._get_topic_name(module_name)
        result, mid = self._client.unsubscribe(topic)
        
        with self._buffer_lock:
            if module_name in self._event_buffers:
                del self._event_buffers[module_name]
        
        return result == mqtt.MQTT_ERR_SUCCESS

    def get_events_for_module(self, module_name: str) -> List[Event]:
        """
        Получает события из буфера модуля (pull-модель).
        
        Args:
            module_name: Имя модуля
            
        Returns:
            List[Event]: Список событий из буфера модуля
        """
        with self._buffer_lock:
            if module_name not in self._event_buffers:
                return []
            
            events = self._event_buffers[module_name].copy()
            self._event_buffers[module_name].clear()
            return events

    def disconnect(self):
        """Отключается от MQTT broker."""
        self._client.loop_stop()
        self._client.disconnect()
