"""
E2E тесты DronePort через реальный брокер и поднятые docker-контейнеры.
Требуют: make docker-up и make drone-port-system-up.
Если брокер или компоненты недоступны, тесты пропускаются.
"""
import os
import socket
import time
import uuid

import pytest

from systems.drone_port.src.gateway.topics import ExternalTopics as GatewayExternalTopics
from systems.drone_port.src.gateway.topics import GatewayActions, SystemTopics
from systems.drone_port.src.orchestrator.topics import OrchestratorActions


DEFAULT_BROKER_TYPE = "mqtt"


def _broker_available(retries=5, delay=2):
    bt = (
        os.environ.get("BROKER_TYPE", DEFAULT_BROKER_TYPE) or DEFAULT_BROKER_TYPE
    ).lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    port_val = os.environ.get("MQTT_PORT", "1883") if bt == "mqtt" else os.environ.get("KAFKA_PORT", "9092")
    port = int(port_val)
    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(delay)
    return False


def _ensure_broker_env():
    bt = (
        os.environ.get("BROKER_TYPE") or DEFAULT_BROKER_TYPE
    ).lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    kafka_port = os.environ.get("KAFKA_PORT", "9092")
    mqtt_port = os.environ.get("MQTT_PORT", "1883")
    os.environ.setdefault("ADMIN_USER", "admin")
    os.environ.setdefault("ADMIN_PASSWORD", "admin123")
    os.environ.setdefault("BROKER_USER", os.environ["ADMIN_USER"])
    os.environ.setdefault("BROKER_PASSWORD", os.environ["ADMIN_PASSWORD"])
    if bt == "kafka":
        os.environ["BROKER_TYPE"] = "kafka"
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", f"{host}:{kafka_port}"
        )
    else:
        os.environ["BROKER_TYPE"] = "mqtt"
        os.environ["MQTT_BROKER"] = os.environ.get("MQTT_BROKER", host)
        os.environ["MQTT_PORT"] = str(mqtt_port)


@pytest.fixture(scope="module")
def system_bus():
    if not _broker_available():
        pytest.skip(
            f"Broker at {os.environ.get('BROKER_HOST', 'localhost')} not available. "
            "Run: make docker-up"
        )
    _ensure_broker_env()
    from broker.src.bus_factory import create_system_bus

    bus = create_system_bus(client_id=f"drone_port_test_{uuid.uuid4().hex[:8]}")
    bus.start()
    time.sleep(2)
    yield bus
    bus.stop()


def _gateway_request(system_bus, sender: str, action: str, payload: dict, timeout: float = 10.0):
    return system_bus.request(
        SystemTopics.DRONE_PORT,
        {
            "action": GatewayActions.PROXY_REQUEST,
            "sender": sender,
            "payload": {
                "target": {
                    "topic": GatewayExternalTopics.DRONE_PORT,
                    "action": action,
                },
                "data": payload,
            },
        },
        timeout=timeout,
    )


def _gateway_target_response(response: dict) -> dict:
    payload = response.get("payload", {})
    target_response = payload.get("target_response", {})
    return target_response if isinstance(target_response, dict) else {}


def test_get_available_drones_via_gateway(system_bus):
    gateway_response = _gateway_request(
        system_bus,
        GatewayExternalTopics.OPERATOR,
        OrchestratorActions.GET_AVAILABLE_DRONES,
        {},
    )
    if gateway_response is None:
        pytest.skip("No response from gateway. Run: make drone-port-system-up")

    orchestrator_response = _gateway_target_response(gateway_response)
    assert orchestrator_response.get("success") is True
    payload = orchestrator_response["payload"]
    assert isinstance(payload.get("drones"), list)
    assert "from" in payload


def test_landing_flow_via_gateway_makes_drone_available(system_bus):
    drone_id = f"DR-LAND-{uuid.uuid4().hex[:6]}"

    landing_response = _gateway_request(
        system_bus,
        GatewayExternalTopics.AGRODRON,
        GatewayActions.REQUEST_LANDING,
        {"drone_id": drone_id, "model": "TestModel", "battery": 95.0},
    )
    if landing_response is None:
        pytest.skip("No response from gateway. Run: make drone-port-system-up")

    drone_manager_response = _gateway_target_response(landing_response)
    assert drone_manager_response.get("success") is True
    landing_payload = drone_manager_response["payload"]
    assert landing_payload.get("approved") is True
    assert landing_payload.get("drone_id") == drone_id

    available_response = None
    for _ in range(15):
        available_response = _gateway_request(
            system_bus,
            GatewayExternalTopics.OPERATOR,
            OrchestratorActions.GET_AVAILABLE_DRONES,
            {},
        )
        available_payload = _gateway_target_response(available_response or {}).get("payload", {})
        drones = available_payload.get("drones", [])
        if any(drone.get("drone_id") == drone_id for drone in drones):
            break
        time.sleep(1)

    if available_response is None:
        pytest.skip("No response from gateway. Run: make drone-port-system-up")

    available_payload = _gateway_target_response(available_response).get("payload", {})
    drones = available_payload.get("drones", [])
    assert any(drone.get("drone_id") == drone_id for drone in drones)
