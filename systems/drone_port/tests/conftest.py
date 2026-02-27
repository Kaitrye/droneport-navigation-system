"""
Общие фикстуры для всех тестов Droneport.
Соответствует требованию: выделить конфигурацию в отдельный файл.
"""

import pytest
from unittest.mock import Mock, MagicMock
from components.state_store.src.state_store import StateStore


@pytest.fixture
def mock_redis():
    """Мок Redis-клиента."""
    mock = Mock()
    mock.hset.return_value = True
    mock.hgetall.return_value = {}
    mock.keys.return_value = []
    return mock


@pytest.fixture
def state_store(mock_redis):
    """Фикстура: StateStore с моком Redis."""
    store = StateStore()
    store.redis = mock_redis
    return store


@pytest.fixture
def mock_bus():
    """Мок SystemBus для изоляции от реального брокера."""
    bus = Mock()
    bus.request = Mock(return_value=None)
    bus.respond = Mock()
    bus.publish = Mock()
    return bus