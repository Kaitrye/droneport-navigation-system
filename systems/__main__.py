"""Точка входа для систем: python -m systems.

Тип системы выбирается через переменную окружения SYSTEM_TYPE:
    - dummy (по умолчанию)
    - gcs_* (компоненты наземной управляющей станции)
"""
import os
import sys

from broker.bus_factory import create_system_bus
from systems.dummy_system.src.dummy import DummySystem
from systems.gcs.components import (
    FleetComponent,
    MissionComponent,
    OrchestratorComponent,
    RedisComponent,
    RobotComponent,
    TelemetryComponent,
)


def main() -> None:
    system_type = os.environ.get("SYSTEM_TYPE", "dummy").strip().lower()
    system_id = os.environ.get("SYSTEM_ID", f"{system_type}_001")
    health_port = int(os.environ.get("HEALTH_PORT", "0") or "0")
    name = os.environ.get("SYSTEM_NAME", system_id.replace("_", " ").title())

    bus = create_system_bus(client_id=system_id)

    if system_type == "dummy":
        system = DummySystem(
            system_id=system_id,
            name=name,
            bus=bus,
            health_port=health_port or None,
        )
    elif system_type in {"gcs_mission", "mission"}:
        system = MissionComponent(system_id=system_id, bus=bus, health_port=health_port or None)
    elif system_type in {"gcs_orchestrator", "orchestrator"}:
        system = OrchestratorComponent(system_id=system_id, bus=bus, health_port=health_port or None)
    elif system_type in {"gcs_fleet", "fleet"}:
        system = FleetComponent(system_id=system_id, bus=bus, health_port=health_port or None)
    elif system_type in {"gcs_robot", "robot"}:
        system = RobotComponent(system_id=system_id, bus=bus, health_port=health_port or None)
    elif system_type in {"gcs_telemetry", "telemetry"}:
        system = TelemetryComponent(system_id=system_id, bus=bus, health_port=health_port or None)
    elif system_type in {"gcs_redis", "redis"}:
        system = RedisComponent(system_id=system_id, bus=bus, health_port=health_port or None)
    else:
        print(
            "Unsupported SYSTEM_TYPE. Use 'dummy' or one of: gcs_mission, gcs_orchestrator, gcs_fleet, gcs_robot, gcs_telemetry, gcs_redis",
            file=sys.stderr,
        )
        sys.exit(1)

    system.run_forever()


if __name__ == "__main__":
    main()
