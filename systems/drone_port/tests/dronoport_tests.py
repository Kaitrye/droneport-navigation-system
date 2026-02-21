"""
Юнит-тесты для DroneportSystem.
Требования ТЗ:
- КК9: использование pytest
- КК10: покрытие через pytest-cov
- КК7: каждый тест должен включать setup/teardown, запрещено делиться данными между тестами
- Д9: все функции/методы должны иметь docstring (соблюдено в тестируемом коде)
"""

import pytest
from unittest.mock import Mock, MagicMock, patch
from typing import Dict, Any
from systems.droneport_system.src.droneport_system import DroneportSystem
from shared.topics import SystemTopics, DroneportActions


class TestDroneportSystem:
    """Тесты логики Дронопорта без реального брокера (моки)."""

    @pytest.fixture
    def mock_bus(self) -> Mock:
        """Фикстура: мок брокера сообщений."""
        bus = Mock()
        bus.request = Mock(return_value=None)
        bus.respond = Mock()
        bus.publish = Mock()
        return bus

    @pytest.fixture
    def droneport(self, mock_bus: Mock) -> DroneportSystem:
        """Фикстура: чистый экземпляр Дронопорта для каждого теста."""
        # Важно: каждый тест получает НОВЫЙ экземпляр (изоляция по КК7)
        system = DroneportSystem(
            system_id="droneport-test-001",
            name="TestDroneport",
            bus=mock_bus,
            health_port=None
        )
        return system

    # =========================================================================
    # Тесты обработки посадки (ОФ1)
    # =========================================================================

    def test_landing_success(self, droneport: DroneportSystem):
        """Успешная посадка дрона на свободный порт."""
        message = {
            "payload": {
                "drone_id": "D-TEST-001",
                "port_id": "P-01",
                "battery_level": 45.0
            }
        }

        result = droneport._handle_request_landing(message)

        assert result["status"] == "landed"
        assert result["drone_id"] == "D-TEST-001"
        assert result["port_id"] == "P-01"
        assert "message" in result

        # Проверяем внутреннее состояние
        assert "D-TEST-001" in droneport._drones
        assert droneport._drones["D-TEST-001"]["battery_level"] == 45.0
        assert droneport._drones["D-TEST-001"]["status"] == "landed"

        assert "P-01" in droneport._ports
        assert droneport._ports["P-01"]["drone_id"] == "D-TEST-001"
        assert droneport._ports["P-01"]["status"] == "occupied"

    def test_landing_rejected_port_occupied(self, droneport: DroneportSystem):
        """Отказ в посадке: порт уже занят другим дроном."""
        # Сначала посадим первый дрон
        droneport._handle_request_landing({
            "payload": {
                "drone_id": "D-TEST-001",
                "port_id": "P-01",
                "battery_level": 60.0
            }
        })

        # Попытка посадить второй дрон на тот же порт
        result = droneport._handle_request_landing({
            "payload": {
                "drone_id": "D-TEST-002",
                "port_id": "P-01",
                "battery_level": 30.0
            }
        })

        assert result["status"] == "rejected"
        assert result["message"] == "Port P-01 is occupied"
        assert "D-TEST-002" not in droneport._drones  # Второй дрон НЕ добавлен

    def test_landing_rejected_missing_drone_id(self, droneport: DroneportSystem):
        """Отказ в посадке: не указан drone_id."""
        result = droneport._handle_request_landing({
            "payload": {
                "port_id": "P-01",
                "battery_level": 50.0
            }
        })

        assert "error" in result
        assert result["error"] == "drone_id_required"
        assert len(droneport._drones) == 0  # Никаких дронов не добавлено

    def test_landing_rejected_missing_port_id(self, droneport: DroneportSystem):
        """Отказ в посадке: не указан port_id."""
        result = droneport._handle_request_landing({
            "payload": {
                "drone_id": "D-TEST-001",
                "battery_level": 50.0
            }
        })

        assert "error" in result
        assert result["error"] == "port_id_required"
        assert len(droneport._drones) == 0

    # =========================================================================
    # Тесты генерации списка дронов (ОФ3 + ОФ4)
    # =========================================================================

    def test_get_port_status_empty(self, droneport: DroneportSystem):
        """Получение статуса порта: нет дронов."""
        message = {"payload": {}}
        result = droneport._handle_get_port_status(message)

        assert result["total"] == 0
        assert result["drones"] == []
        assert "timestamp" in result

    def test_get_port_status_with_drones(self, droneport: DroneportSystem):
        """Получение статуса порта: несколько дронов с разным состоянием."""
        # Добавляем 3 дрона с разным уровнем батареи
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-001", "port_id": "P-01", "battery_level": 85.0}
        })
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-002", "port_id": "P-02", "battery_level": 15.0}  # низкий заряд
        })
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-003", "port_id": "P-03", "battery_level": 40.0}
        })

        # Запускаем зарядку для D-003
        droneport._handle_start_charging({
            "payload": {
                "drone_id": "D-003",
                "target_battery": 90.0,
                "departure_time_sec": 1800
            }
        })

        result = droneport._handle_get_port_status({"payload": {}})

        assert result["total"] == 3
        drones = {d["drone_id"]: d for d in result["drones"]}

        # Проверяем состояние каждого дрона
        assert drones["D-001"]["battery_level"] == 85.0
        assert drones["D-001"]["safety_target"] == "normal_operation"
        assert drones["D-001"]["issues"] == []

        assert drones["D-002"]["battery_level"] == 15.0
        assert drones["D-002"]["safety_target"] == "low_battery_alert"
        assert "battery_critical" in drones["D-002"]["issues"]

        assert drones["D-003"]["battery_level"] == 40.0
        assert drones["D-003"]["charging_power_w"] > 0
        assert drones["D-003"]["safety_target"] == "normal_operation"

    def test_get_port_status_with_filter(self, droneport: DroneportSystem):
        """Фильтрация списка дронов по статусу."""
        # Добавляем дроны
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-001", "port_id": "P-01", "battery_level": 90.0}
        })
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-002", "port_id": "P-02", "battery_level": 30.0}
        })
        # Запускаем зарядку для D-002
        droneport._handle_start_charging({
            "payload": {
                "drone_id": "D-002",
                "target_battery": 90.0,
                "departure_time_sec": 3600
            }
        })

        # Фильтр: только заряжающиеся
        result = droneport._handle_get_port_status({
            "payload": {"filter": "charging"}
        })
        assert result["total"] == 1
        assert result["drones"][0]["drone_id"] == "D-002"

        # Фильтр: все посадившиеся
        result = droneport._handle_get_port_status({
            "payload": {"filter": "landed"}
        })
        assert result["total"] == 2

    # =========================================================================
    # Тесты взлёта (ОФ2)
    # =========================================================================

    def test_takeoff_success(self, droneport: DroneportSystem):
        """Успешный взлёт дрона."""
        # Сначала посадка
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-TEST-001", "port_id": "P-01", "battery_level": 70.0}
        })

        # Затем взлёт
        result = droneport._handle_request_takeoff({
            "payload": {"drone_id": "D-TEST-001"}
        })

        assert result["status"] == "takeoff_approved"
        assert result["drone_id"] == "D-TEST-001"
        assert result["battery_level"] == 70.0

        # Проверяем, что дрон удалён из системы
        assert "D-TEST-001" not in droneport._drones
        assert droneport._ports["P-01"]["drone_id"] is None  # порт освобождён

    def test_takeoff_drone_not_found(self, droneport: DroneportSystem):
        """Попытка взлёта несуществующего дрона."""
        result = droneport._handle_request_takeoff({
            "payload": {"drone_id": "NON-EXISTENT"}
        })

        assert result["status"] == "not_found"
        assert result["drone_id"] == "NON-EXISTENT"

    # =========================================================================
    # Тесты зарядки (ПРФ1)
    # =========================================================================

    def test_start_charging_success(self, droneport: DroneportSystem):
        """Успешный запуск зарядки с расчётом мощности."""
        # Посадка дрона
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-CHARGE", "port_id": "P-01", "battery_level": 30.0}
        })

        # Запуск зарядки: нужно зарядить до 90% за 1 час
        result = droneport._handle_start_charging({
            "payload": {
                "drone_id": "D-CHARGE",
                "target_battery": 90.0,
                "departure_time_sec": 3600  # 1 час
            }
        })

        assert result["status"] == "charging_started"
        assert result["drone_id"] == "D-CHARGE"
        assert result["charging_power_w"] > 0
        assert result["estimated_finish_sec"] > 0

        # Проверяем внутреннее состояние
        assert droneport._drones["D-CHARGE"]["charging_power_w"] == result["charging_power_w"]
        assert droneport._ports["P-01"]["charging_power_w"] == result["charging_power_w"]
        assert droneport._ports["P-01"]["status"] == "charging"

    def test_start_charging_already_sufficient(self, droneport: DroneportSystem):
        """Запрос зарядки, когда батарея уже на целевом уровне."""
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-FULL", "port_id": "P-01", "battery_level": 95.0}
        })

        result = droneport._handle_start_charging({
            "payload": {
                "drone_id": "D-FULL",
                "target_battery": 90.0,  # уже выше цели
                "departure_time_sec": 3600
            }
        })

        assert result["status"] == "already_sufficient"
        assert result["battery_level"] == 95.0

    def test_stop_charging(self, droneport: DroneportSystem):
        """Остановка зарядки."""
        # Посадка + запуск зарядки
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-STOP", "port_id": "P-01", "battery_level": 40.0}
        })
        droneport._handle_start_charging({
            "payload": {
                "drone_id": "D-STOP",
                "target_battery": 90.0,
                "departure_time_sec": 3600
            }
        })

        # Остановка
        result = droneport._handle_stop_charging({
            "payload": {"drone_id": "D-STOP"}
        })

        assert result["status"] == "charging_stopped"
        assert droneport._ports["P-01"]["charging_power_w"] == 0.0
        assert droneport._ports["P-01"]["status"] == "idle"

    # =========================================================================
    # Тесты расширенного статуса системы
    # =========================================================================

    def test_get_status_metrics(self, droneport: DroneportSystem):
        """Проверка метрик в расширенном статусе системы."""
        # Добавляем дроны
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-1", "port_id": "P-1", "battery_level": 80.0}
        })
        droneport._handle_request_landing({
            "payload": {"drone_id": "D-2", "port_id": "P-2", "battery_level": 20.0}
        })
        droneport._handle_start_charging({
            "payload": {
                "drone_id": "D-2",
                "target_battery": 90.0,
                "departure_time_sec": 1800
            }
        })

        status = droneport.get_status()

        assert status["system_type"] == "droneport"
        assert status["name"] == "TestDroneport"
        assert status["drones_total"] == 2
        assert status["ports_total"] == 2
        assert status["ports_occupied"] == 2
        assert status["charging_active"] == 1  # только D-2 заряжается

    # =========================================================================
    # Граничные случаи и валидация
    # =========================================================================

    @pytest.mark.parametrize("battery_level", [-10, 110, "invalid", None])
    def test_landing_invalid_battery_level(self, droneport: DroneportSystem, battery_level):
        """Обработка некорректного уровня батареи при посадке."""
        message = {
            "payload": {
                "drone_id": "D-INVALID",
                "port_id": "P-01",
                "battery_level": battery_level
            }
        }

        # Система должна обработать без падения (защита от некорректных данных)
        try:
            result = droneport._handle_request_landing(message)
            # Даже при некорректных данных система не должна падать
            assert isinstance(result, dict)
        except Exception as e:
            pytest.fail(f"Система упала при обработке некорректных данных: {e}")

    def test_multiple_landings_different_ports(self, droneport: DroneportSystem):
        """Последовательная посадка нескольких дронов на разные порты."""
        ports = ["P-01", "P-02", "P-03"]
        drones = ["D-001", "D-002", "D-003"]

        for drone_id, port_id in zip(drones, ports):
            result = droneport._handle_request_landing({
                "payload": {
                    "drone_id": drone_id,
                    "port_id": port_id,
                    "battery_level": 50.0
                }
            })
            assert result["status"] == "landed"

        # Проверяем итоговое состояние
        assert len(droneport._drones) == 3
        assert len(droneport._ports) == 3
        for port_id in ports:
            assert droneport._ports[port_id]["status"] == "occupied"