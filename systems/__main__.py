"""Точка входа для систем: python -m systems.

Тип системы выбирается через переменную окружения SYSTEM_TYPE:
    - dummy (по умолчанию)
    - nus   (Наземная управляющая станция)
"""
import os
import sys

from broker.bus_factory import create_system_bus
from systems.dummy_system.src.dummy import DummySystem
from systems.nus_system.src.nus_system import NUSSystem


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
    elif system_type == "nus":
        system = NUSSystem(
            system_id=system_id,
            name=name,
            bus=bus,
            health_port=health_port or None,
        )
    else:
        print(
            "Unsupported SYSTEM_TYPE. Use 'dummy' or 'nus'", file=sys.stderr
        )
        sys.exit(1)

    system.run_forever()


if __name__ == "__main__":
    main()
