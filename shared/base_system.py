"""
Базовый класс для всех систем, использующих SystemBus.

Предоставляет унифицированный интерфейс для:
- Подписки на топик системы
- Обработки входящих сообщений
- Маршрутизации по action
- Health check endpoint
"""
from abc import ABC, abstractmethod
from typing import Dict, Any, Callable, Optional
import threading
import signal
import sys

try:
    from flask import Flask, jsonify
    FLASK_AVAILABLE = True
except ImportError:
    Flask = Any  # type: ignore
    jsonify = None  # type: ignore
    FLASK_AVAILABLE = False

from broker.system_bus import SystemBus
from shared.messages import create_response


class BaseSystem(ABC):
    """
    Абстрактный базовый класс для всех систем.
    
    Каждая система:
    - Подключается к SystemBus
    - Подписывается на свой топик
    - Обрабатывает сообщения через маршрутизацию по action
    - Имеет health check endpoint
    
    Attributes:
        system_id: Уникальный идентификатор экземпляра системы
        system_type: Тип системы (certification, fleet, etc.)
        topic: Топик для получения сообщений
        bus: SystemBus для коммуникации
    """

    def __init__(
        self, 
        system_id: str,
        system_type: str,
        topic: str,
        bus: SystemBus,
        health_port: Optional[int] = None
    ):
        """
        Инициализация системы.
        
        Args:
            system_id: Уникальный ID экземпляра (например, "certification_001")
            system_type: Тип системы (например, "certification")
            topic: Топик для подписки (например, "systems.certification")
            bus: Экземпляр SystemBus
            health_port: Порт для health check (опционально)
        """
        self.system_id = system_id
        self.system_type = system_type
        self.topic = topic
        self.bus = bus
        self.health_port = health_port
        
        # Маршрутизатор action -> handler
        self._handlers: Dict[str, Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]] = {}
        
        # Flask app для health check
        self._health_app: Optional[Flask] = None
        self._health_thread: Optional[threading.Thread] = None
        
        # Флаг работы
        self._running = False
        
        # Регистрируем базовые обработчики
        self._setup_handlers()
        
        # Регистрируем обработчики конкретной системы
        self._register_handlers()

    def _setup_handlers(self):
        """Регистрирует базовые обработчики."""
        self.register_handler("ping", self._handle_ping)
        self.register_handler("get_status", self._handle_get_status)

    @abstractmethod
    def _register_handlers(self):
        """
        Регистрирует обработчики сообщений для конкретной системы.
        
        Должен быть реализован в каждой системе.
        
        Пример:
            self.register_handler("certify_firmware", self._handle_certify)
            self.register_handler("check_firmware", self._handle_check)
        """
        pass

    def register_handler(
        self, 
        action: str, 
        handler: Callable[[Dict[str, Any]], Optional[Dict[str, Any]]]
    ):
        """
        Регистрирует обработчик для действия.
        
        Args:
            action: Название действия (например, "certify_firmware")
            handler: Функция-обработчик, принимает message dict,
                     возвращает payload для ответа или None
        """
        self._handlers[action] = handler
        
    def _handle_message(self, message: Dict[str, Any]):
        """
        Обрабатывает входящее сообщение.
        
        Маршрутизирует по полю "action" к соответствующему обработчику.
        Автоматически отправляет ответ, если есть reply_to.
        
        Args:
            message: Входящее сообщение
        """
        action = message.get("action")
        
        if not action:
            print(f"[{self.system_id}] Message without action: {message}")
            return
        
        handler = self._handlers.get(action)
        
        if not handler:
            print(f"[{self.system_id}] Unknown action: {action}")
            # Отправляем ошибку, если есть reply_to
            if message.get("reply_to"):
                self.bus.respond(
                    message, 
                    {"error": f"Unknown action: {action}"},
                    action="error"
                )
            return
        
        try:
            # Вызываем обработчик
            result = handler(message)
            
            # Отправляем ответ, если есть reply_to и результат
            if message.get("reply_to") and result is not None:
                response = create_response(
                    correlation_id=message.get("correlation_id"),
                    payload=result,
                    sender=self.system_id,
                    success=True
                )
                self.bus.publish(message["reply_to"], response)
                
        except Exception as e:
            print(f"[{self.system_id}] Error handling {action}: {e}")
            # Отправляем ошибку
            if message.get("reply_to"):
                response = create_response(
                    correlation_id=message.get("correlation_id"),
                    payload={},
                    sender=self.system_id,
                    success=False,
                    error=str(e)
                )
                self.bus.publish(message["reply_to"], response)

    def _handle_ping(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработчик ping - возвращает pong."""
        return {"pong": True, "system_id": self.system_id}

    def _handle_get_status(self, message: Dict[str, Any]) -> Dict[str, Any]:
        """Обработчик get_status - возвращает статус системы."""
        return self.get_status()

    def get_status(self) -> Dict[str, Any]:
        """
        Возвращает статус системы.
        
        Может быть переопределён в наследниках для добавления
        специфичных метрик.
        
        Returns:
            Dict со статусом системы
        """
        return {
            "system_id": self.system_id,
            "system_type": self.system_type,
            "topic": self.topic,
            "running": self._running,
            "handlers": list(self._handlers.keys())
        }

    def _setup_health_check(self):
        """Настраивает Flask app для health check."""
        if not self.health_port:
            return

        if not FLASK_AVAILABLE:
            print(
                f"[{self.system_id}] Flask is not installed; health endpoint is disabled"
            )
            return
        
        self._health_app = Flask(f"{self.system_type}_health")
        
        # Отключаем логи Flask
        import logging
        log = logging.getLogger('werkzeug')
        log.setLevel(logging.ERROR)
        
        @self._health_app.route('/health')
        def health():
            return jsonify({
                "status": "healthy" if self._running else "starting",
                "system_id": self.system_id,
                "system_type": self.system_type
            })
        
        @self._health_app.route('/status')
        def status():
            return jsonify(self.get_status())

    def _run_health_server(self):
        """Запускает health check сервер в отдельном потоке."""
        if self._health_app and self.health_port:
            self._health_app.run(
                host='0.0.0.0', 
                port=self.health_port, 
                threaded=True,
                use_reloader=False
            )

    def start(self):
        """
        Запускает систему.
        
        - Запускает SystemBus
        - Подписывается на топик
        - Запускает health check сервер (если задан порт)
        """
        print(f"[{self.system_id}] Starting {self.system_type}...")
        
        # Запускаем SystemBus
        self.bus.start()
        
        # Подписываемся на свой топик
        self.bus.subscribe(self.topic, self._handle_message)
        
        self._running = True
        
        # Запускаем health check
        self._setup_health_check()
        if self._health_app and self.health_port:
            self._health_thread = threading.Thread(
                target=self._run_health_server,
                daemon=True,
                name=f"{self.system_type}-health"
            )
            self._health_thread.start()
            print(f"[{self.system_id}] Health check on port {self.health_port}")
        
        print(f"[{self.system_id}] Started. Listening on topic: {self.topic}")

    def stop(self):
        """Останавливает систему."""
        print(f"[{self.system_id}] Stopping...")
        
        self._running = False
        
        # Отписываемся от топика
        self.bus.unsubscribe(self.topic)
        
        # Останавливаем SystemBus
        self.bus.stop()
        
        print(f"[{self.system_id}] Stopped")

    def run_forever(self):
        """
        Запускает систему и блокирует до получения сигнала остановки.
        
        Обрабатывает SIGINT и SIGTERM для graceful shutdown.
        """
        # Обработчик сигналов
        def signal_handler(sig, frame):
            print(f"\n[{self.system_id}] Received signal {sig}, shutting down...")
            self.stop()
            sys.exit(0)
        
        signal.signal(signal.SIGINT, signal_handler)
        signal.signal(signal.SIGTERM, signal_handler)
        
        self.start()
        
        print(f"[{self.system_id}] Running. Press Ctrl+C to stop.")
        
        # Блокируем главный поток
        try:
            while self._running:
                signal.pause()
        except AttributeError:
            # Windows не поддерживает signal.pause()
            import time
            while self._running:
                time.sleep(1)
