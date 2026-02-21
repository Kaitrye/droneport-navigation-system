"""
Константы топиков для SystemBus.

Политика: 1 топик = 1 система/модуль
Маршрутизация по полю "action" внутри сообщения.
"""


# ============================================================================
# Топики для систем (systems)
# ============================================================================

class SystemTopics:
    """Топики для межсистемного взаимодействия."""

    # Существующая учебная система
    DUMMY = "systems.dummy"

    # Наземная управляющая станция (НУС / GCS)
    NUS = "systems.nus"

    # Дронопорт (инфраструктура посадки/зарядки)
    DRONEPORT = "systems.droneport"

    @classmethod
    def all(cls) -> list:
        """Возвращает список всех системных топиков."""
        return [
            cls.DUMMY,
            cls.NUS,
            cls.DRONEPORT,
        ]


# ============================================================================
# Actions для dummy системы
# ============================================================================

class DummyActions:
    """Действия для dummy системы."""
    ECHO = "echo"
    PROCESS = "process"
    RESPONSE = "response"


# ============================================================================
# Actions для НУС (Nazemnaya Upravlyayushchaya Stantsiya / GCS)
# ============================================================================


class NUSActions:
    """Действия для НУС.

    Эти действия используются во внешнем API НУС и при
    межсистемном взаимодействии через SystemBus.
    """

    # Миссии для отдельных БВС
    CREATE_MISSION = "create_mission"  # ФО1: формирование миссии по координатам
    IMPORT_MISSION_WPL = "import_mission_wpl"  # ФО2: импорт миссии из WPL
    START_MISSION = "start_mission"  # ФО3: запуск миссии
    CANCEL_MISSION = "cancel_mission"  # ФО4: отмена миссии

    # Мониторинг
    GET_DRONE_STATUS = "get_drone_status"  # ФО5: мониторинг состояния/положения дрона

    # Групповое управление
    CREATE_GROUP = "create_group"  # ФО6: создание группы дронов
    ASSIGN_GROUP_MISSION = "assign_group_mission"  # ФО6: задание миссии для группы
    CANCEL_GROUP_MISSION = "cancel_group_mission"  # ФО6: отмена миссии группы

    # Унифицированный ответ
    RESPONSE = "response"


# ============================================================================
# Actions для системы Дронопорта (минимальный скелет на будущее)
# ============================================================================


class DroneportActions:
    """Действия для Дронопорта.

    Пока используются как заготовка для будущей реализации
    управления посадочными местами и зарядкой.
    """

    REQUEST_LANDING = "request_landing"
    REQUEST_TAKEOFF = "request_takeoff"
    START_CHARGING = "start_charging"
    STOP_CHARGING = "stop_charging"
    GET_PORT_STATUS = "get_port_status"
    RESPONSE = "response"
