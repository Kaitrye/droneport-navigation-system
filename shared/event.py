from dataclasses import dataclass
from typing import Any, Optional


@dataclass
class Event:
    """Формат событий для обработки"""

    source: str  # отправитель
    destination: str  # получатель - название очереди блока-получателя, \
    # в которую нужно отправить сообщение
    operation: str  # чего хочет (запрашиваемое действие)
    parameters: Any = None  # с какими параметрами
    extra_parameters: Any = None  # доп. параметры
    signature: Optional[str] = None  # цифровая подпись или аналог \
    # для проверки целостности и аутентичности сообщения

    def to_dict(self) -> dict:
        """Конвертирует событие в словарь для передачи"""
        return {
            "source": self.source,
            "destination": self.destination,
            "operation": self.operation,
            "parameters": self.parameters,
            "extra_parameters": self.extra_parameters,
            "signature": self.signature,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "Event":
        """Создает событие из словаря"""
        return cls(
            source=data.get("source", ""),
            destination=data.get("destination", ""),
            operation=data.get("operation", ""),
            parameters=data.get("parameters", {}),
            extra_parameters=data.get("extra_parameters"),
            signature=data.get("signature"),
        )

    def __str__(self) -> str:
        return f"Event({self.source} -> {self.destination}: {self.operation})"
