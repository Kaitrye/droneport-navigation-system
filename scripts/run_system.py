"""Запуск DummySystem. Env: SYSTEM_ID, SYSTEM_NAME, HEALTH_PORT, BROKER_TYPE, BROKER_USER, BROKER_PASSWORD."""
import os
import sys

from broker.bus_factory import create_system_bus
from systems.dummy_system.src.dummy import DummySystem


def main():
    system_id = os.environ.get("SYSTEM_ID", "dummy_001")
    name = os.environ.get("SYSTEM_NAME", system_id.replace("_", " ").title())
    health_port = int(os.environ.get("HEALTH_PORT", "0") or "0")

    bus = create_system_bus(client_id=system_id)
    system = DummySystem(
        system_id=system_id,
        name=name,
        bus=bus,
        health_port=health_port or None,
    )
    system.run_forever()


if __name__ == "__main__":
    main()
