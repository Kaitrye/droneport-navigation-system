"""
Kafka реализация EventBus для распределенной передачи событий.
Требует запущенный Apache Kafka broker.
"""
import json
import os
import threading
import time
from typing import Callable, Dict, List

try:
    from kafka import KafkaProducer, KafkaConsumer
    from kafka.errors import KafkaError
    KAFKA_AVAILABLE = True
except ImportError:
    KAFKA_AVAILABLE = False

from broker import EventBus
from shared.event import Event
from shared.ports import get_kafka_bootstrap


class KafkaEventBus(EventBus):
    """
    Реализация EventBus на основе Apache Kafka.
    
    Каждый модуль использует свой топик: drone.{module_name}.events
    События сериализуются в JSON для передачи через Kafka.
    """

    def __init__(self, bootstrap_servers: str = None, client_id: str = "drone_event_bus"):
        """
        Инициализация Kafka EventBus.
        
        Args:
            bootstrap_servers: Адрес Kafka broker (например, "localhost:9092")
            client_id: Идентификатор клиента Kafka
        """
        if not KAFKA_AVAILABLE:
            raise ImportError(
                "kafka-python is not installed. Install it with: pip install kafka-python"
            )

        self.bootstrap_servers = bootstrap_servers or get_kafka_bootstrap()
        self.client_id = client_id
        self.username = os.environ.get("BROKER_USER")
        self.password = os.environ.get("BROKER_PASSWORD")
        
        self._producer = KafkaProducer(
            bootstrap_servers=self.bootstrap_servers,
            client_id=client_id,
            value_serializer=lambda v: json.dumps(v).encode('utf-8'),
            **self._get_sasl_config()
        )
        
        # Словарь consumers для каждого модуля (для pull-модели)
        self._consumers: Dict[str, KafkaConsumer] = {}
        # Словарь callback-функций для push-модели
        self._callbacks: Dict[str, Callable[[Event], None]] = {}
        # Словарь потоков для обработки сообщений
        self._consumer_threads: Dict[str, threading.Thread] = {}
        # Флаг для остановки потоков
        self._running: Dict[str, bool] = {}

    def _get_sasl_config(self) -> dict:
        if self.username and self.password:
            return {
                'security_protocol': 'SASL_PLAINTEXT',
                'sasl_mechanism': 'PLAIN',
                'sasl_plain_username': self.username,
                'sasl_plain_password': self.password
            }
        return {}

    def _get_topic_name(self, module_name: str) -> str:
        """Формирует имя топика для модуля."""
        return f"drone.{module_name}.events"

    def publish(self, event: Event, destination: str) -> bool:
        """
        Отправляет событие в Kafka топик модуля-получателя.
        
        Args:
            event: Событие для отправки
            destination: Имя модуля-получателя
            
        Returns:
            bool: True если событие успешно отправлено
        """
        topic = self._get_topic_name(destination)
        event_dict = event.to_dict()
        
        try:
            future = self._producer.send(topic, event_dict)
            # Ожидаем подтверждения отправки
            future.get(timeout=5)
            return True
        except KafkaError as e:
            print(f"Error publishing event to Kafka topic {topic}: {e}")
            return False

    def _consumer_loop(self, module_name: str):
        """
        Цикл обработки сообщений из Kafka для модуля.
        Работает в отдельном потоке.
        
        Args:
            module_name: Имя модуля
        """
        consumer = self._consumers.get(module_name)
        callback = self._callbacks.get(module_name)
        
        if not consumer or not callback:
            return
        
        while self._running.get(module_name, False):
            try:
                # Читаем сообщения с таймаутом
                messages = consumer.poll(timeout_ms=100)
                for topic_partition, records in messages.items():
                    for record in records:
                        try:
                            event_dict = record.value
                            event = Event.from_dict(event_dict)
                            callback(event)
                        except Exception as e:
                            print(f"Error processing Kafka message for {module_name}: {e}")
            except Exception as e:
                if self._running.get(module_name, False):
                    print(f"Error in Kafka consumer loop for {module_name}: {e}")

    def subscribe(
        self, module_name: str, callback: Callable[[Event], None]
    ) -> bool:
        """
        Подписывает модуль на получение событий из Kafka топика.
        
        Args:
            module_name: Имя модуля-подписчика
            callback: Функция-обработчик события
            
        Returns:
            bool: True если подписка успешна
        """
        self._callbacks[module_name] = callback
        
        topic = self._get_topic_name(module_name)
        consumer = KafkaConsumer(
            topic,
            bootstrap_servers=self.bootstrap_servers,
            client_id=f"{self.client_id}_{module_name}",
            value_deserializer=lambda m: json.loads(m.decode('utf-8')),
            auto_offset_reset='latest',
            enable_auto_commit=True,
            **self._get_sasl_config()
        )
        self._consumers[module_name] = consumer
        
        # Запускаем фоновый поток для обработки сообщений
        self._running[module_name] = True
        thread = threading.Thread(
            target=self._consumer_loop,
            args=(module_name,),
            daemon=True
        )
        thread.start()
        self._consumer_threads[module_name] = thread
        
        # Даем consumer время на инициализацию
        time.sleep(0.1)
        
        return True

    def unsubscribe(self, module_name: str) -> bool:
        """
        Отписывает модуль от получения событий.
        
        Args:
            module_name: Имя модуля
            
        Returns:
            bool: True если отписка успешна
        """
        # Останавливаем поток обработки
        self._running[module_name] = False
        
        # Ждем завершения потока
        if module_name in self._consumer_threads:
            thread = self._consumer_threads[module_name]
            thread.join(timeout=1)
            del self._consumer_threads[module_name]
        
        if module_name in self._callbacks:
            del self._callbacks[module_name]
        
        if module_name in self._consumers:
            consumer = self._consumers[module_name]
            consumer.close()
            del self._consumers[module_name]
        
        return True

    def get_events_for_module(self, module_name: str) -> List[Event]:
        """
        Получает события из Kafka топика модуля (pull-модель).
        
        Args:
            module_name: Имя модуля
            
        Returns:
            List[Event]: Список событий из Kafka топика
        """
        if module_name not in self._consumers:
            # Создаем одноразовый consumer для чтения
            topic = self._get_topic_name(module_name)
            consumer = KafkaConsumer(
                topic,
                bootstrap_servers=self.bootstrap_servers,
                client_id=f"{self.client_id}_{module_name}_pull",
                value_deserializer=lambda m: json.loads(m.decode('utf-8')),
                auto_offset_reset='latest',
                consumer_timeout_ms=100,
                **self._get_sasl_config()
            )
            events = []
            for message in consumer:
                event_dict = message.value
                events.append(Event.from_dict(event_dict))
            consumer.close()
            return events
        
        # Используем существующий consumer
        consumer = self._consumers[module_name]
        events = []
        # Читаем доступные сообщения с таймаутом
        consumer.poll(timeout_ms=100)
        for message in consumer:
            event_dict = message.value
            events.append(Event.from_dict(event_dict))
        
        return events
