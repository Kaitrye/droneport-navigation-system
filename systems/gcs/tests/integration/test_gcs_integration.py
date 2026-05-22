"""
E2E тесты GCS через реальный брокер и Docker-контейнеры компонентов.
Требует: make docker-up в systems/gcs.
Если контейнеры/брокер не запущены — тесты пропускаются (skip).
"""
import os
import socket
import threading
import time
from uuid import uuid4

import pytest

from ...src.mission_store.topics import ComponentTopics as MissionStoreTopics
from ...src.mission_store.topics import MissionStoreActions
from ...src.drone_manager.topics import ComponentTopics as DroneManagerTopics
from ...src.drone_manager.topics import DroneManagerActions
from ...src.gateway.topics import ExternalTopics as GatewayExternalTopics
from ...src.gateway.topics import GatewayActions, SystemTopics
from ...src.orchestrator.topics import OrchestratorActions


def _broker_available(retries=5, delay=2):
    bt = os.environ.get("BROKER_TYPE", "kafka").lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    port_val = (
        os.environ.get("MQTT_PORT", "1883")
        if bt == "mqtt"
        else os.environ.get("KAFKA_PORT", "9092")
    )
    port = int(port_val)
    for _ in range(retries):
        try:
            with socket.create_connection((host, port), timeout=2):
                return True
        except (socket.timeout, ConnectionRefusedError, OSError):
            time.sleep(delay)
    return False


def _request_with_retries(system_bus, topic, message, timeout=10.0, retries=3, delay=2.0):
    response = None
    for _ in range(retries):
        response = system_bus.request(topic, message, timeout=timeout)
        if response is not None:
            return response
        time.sleep(delay)
    return response


def _gateway_message(action: str, payload: dict, correlation_id: str | None = None) -> dict:
    message = {
        "action": GatewayActions.PROXY_REQUEST,
        "sender": GatewayExternalTopics.OPERATOR,
        "payload": {
            "target": {
                "topic": GatewayExternalTopics.GCS,
                "action": action,
            },
            "data": payload,
        },
    }
    if correlation_id:
        message["correlation_id"] = correlation_id
    return message


def _gateway_publish_message(action: str, payload: dict, correlation_id: str | None = None) -> dict:
    message = _gateway_message(action, payload, correlation_id=correlation_id)
    message["action"] = GatewayActions.PROXY_PUBLISH
    return message


def _gateway_target_response(response: dict) -> dict:
    payload = response.get("payload", {})
    target_response = payload.get("target_response", {})
    return target_response if isinstance(target_response, dict) else {}


def _wait_mission_in_store(system_bus, mission_id, retries=6, delay=1.5, predicate=None):
    for _ in range(retries):
        response = system_bus.request(
            MissionStoreTopics.MISSION_STORE,
            {
                "action": MissionStoreActions.GET_MISSION,
                "sender": "gcs_integration_test",
                "payload": {"mission_id": mission_id},
            },
            timeout=10.0,
        )

        if response and response.get("success"):
            mission = response.get("payload", {}).get("mission")
            if mission:
                if predicate is None or predicate(mission):
                    return mission
        time.sleep(delay)

    return None


def _build_task_payload(start_lat=55.751244, start_lon=37.618423, end_lat=55.761244, end_lon=37.628423):
    return {
        "waypoints": [
            {"lat": start_lat, "lon": start_lon, "alt_m": 120},
            {"lat": end_lat, "lon": end_lon, "alt_m": 130},
        ],
    }


def _submit_task_via_gateway(system_bus, payload: dict, correlation_id: str | None = None):
    response = _request_with_retries(
        system_bus,
        SystemTopics.GCS,
        _gateway_message(
            OrchestratorActions.TASK_SUBMIT,
            payload,
            correlation_id=correlation_id,
        ),
        timeout=15.0,
        retries=3,
        delay=3.0,
    )
    if response is None:
        return None
    return _gateway_target_response(response)


def _capture_messages_during(system_bus, topic: str, trigger, expected_count: int, timeout: float = 12.0):
    collected = []
    lock = threading.Lock()

    def _on_message(message):
        with lock:
            collected.append(message)

    system_bus.subscribe(topic, _on_message)
    try:
        trigger()
        deadline = time.time() + timeout
        while time.time() < deadline:
            with lock:
                if len(collected) >= expected_count:
                    return list(collected)
            time.sleep(0.2)
        with lock:
            return list(collected)
    finally:
        system_bus.unsubscribe(topic)


@pytest.fixture(scope="module")
def system_bus():
    if not _broker_available():
        pytest.skip(
            f"Broker ({os.environ.get('BROKER_TYPE', 'kafka')}) "
            f"at {os.environ.get('BROKER_HOST', 'localhost')} not available."
        )
    from broker.src.bus_factory import create_system_bus

    bt = os.environ.get("BROKER_TYPE", "kafka").lower().strip().split("#")[0].strip()
    host = os.environ.get("BROKER_HOST", "localhost")
    kafka_port = os.environ.get("KAFKA_PORT", "9092")
    mqtt_port = os.environ.get("MQTT_PORT", "1883")

    if not os.environ.get("BROKER_USER") and os.environ.get("ADMIN_USER"):
        os.environ["BROKER_USER"] = os.environ["ADMIN_USER"]
    if not os.environ.get("BROKER_PASSWORD") and os.environ.get("ADMIN_PASSWORD"):
        os.environ["BROKER_PASSWORD"] = os.environ["ADMIN_PASSWORD"]
    print(f"Using broker type: {bt}, host: {host}, kafka_port: {kafka_port}, mqtt_port: {mqtt_port}")
    print(f"Using broker credentials: user={os.environ.get('BROKER_USER')}, password={os.environ.get('BROKER_PASSWORD')}")
    if bt == "kafka":
        os.environ["BROKER_TYPE"] = "kafka"
        os.environ["KAFKA_BOOTSTRAP_SERVERS"] = os.environ.get(
            "KAFKA_BOOTSTRAP_SERVERS", f"{host}:{kafka_port}"
        )
    else:
        os.environ["BROKER_TYPE"] = "mqtt"
        os.environ["MQTT_BROKER"] = os.environ.get("MQTT_BROKER", host)
        os.environ["MQTT_PORT"] = str(mqtt_port)

    bus = create_system_bus(client_id="gcs_integration_test")
    bus.start()
    time.sleep(2)

    yield bus

    bus.stop()


def test_task_submit_builds_route_and_saves_mission(system_bus):
    """Orchestrator -> PathPlanner -> MissionStore цепочка через request/response."""
    response = _request_with_retries(
        system_bus,
        SystemTopics.GCS,
        _gateway_message(OrchestratorActions.TASK_SUBMIT, _build_task_payload()),
        timeout=15.0,
        retries=3,
        delay=3.0,
    )

    if response is None:
        pytest.skip("No response from orchestrator. Ensure GCS docker stack is up.")

    assert response.get("success") is True
    target_response = _gateway_target_response(response)
    assert target_response.get("success") is True
    payload = target_response.get("payload", {})
    mission_id = payload.get("mission_id")
    waypoints = payload.get("waypoints", [])

    assert mission_id
    assert isinstance(waypoints, list)
    assert len(waypoints) >= 4

    mission = _wait_mission_in_store(
        system_bus,
        mission_id,
        predicate=lambda mission: mission.get("status") == "created",
    )
    assert mission is not None
    assert mission.get("mission_id") == mission_id
    assert isinstance(mission.get("waypoints"), list)
    assert mission.get("status") == "created"


def test_custom_task_submit_via_gateway_persists_mission(system_bus):
    """Gateway task.submit сохраняет миссию в MissionStore."""
    target_response = _submit_task_via_gateway(
        system_bus,
        {
            "waypoints": [
                {"lat": 59.9311, "lon": 30.3609, "alt_m": 80},
                {"lat": 59.9411, "lon": 30.3709, "alt_m": 95},
            ],
        },
    )

    if target_response is None:
        pytest.skip("No response from gateway. Ensure GCS docker stack is up.")

    assert target_response.get("success") is True
    payload = target_response.get("payload", {})
    mission_id = payload.get("mission_id")
    assert mission_id
    assert isinstance(payload.get("waypoints"), list)
    assert len(payload["waypoints"]) >= 4

    mission = _wait_mission_in_store(
        system_bus,
        mission_id,
        predicate=lambda mission: mission.get("status") == "created",
    )
    assert mission is not None
    assert mission.get("mission_id") == mission_id


def test_task_assign_updates_store_and_publishes_upload(system_bus):
    """Orchestrator task_assign запускает mission upload и обновляет mission_store."""
    drone_id = "dr-it-1"
    correlation_id = f"corr-assign-{uuid4().hex[:8]}"

    planned = _submit_task_via_gateway(system_bus, _build_task_payload())
    if planned is None:
        pytest.skip("No response from gateway. Ensure GCS docker stack is up.")
    mission_id = planned.get("payload", {}).get("mission_id")
    assert mission_id

    def _publish_assign():
        system_bus.publish(
            SystemTopics.GCS,
            _gateway_publish_message(
                OrchestratorActions.TASK_ASSIGN,
                {
                    "mission_id": mission_id,
                    "drone_id": drone_id,
                },
                correlation_id=correlation_id,
            ),
        )
    messages = _capture_messages_during(
        system_bus,
        DroneManagerTopics.DRONE_MANAGER,
        _publish_assign,
        expected_count=1,
        timeout=40.0,
    )

    filtered = [m for m in messages if m.get("correlation_id") == correlation_id]
    assert filtered, "Expected drone_manager upload message for task_assign"
    assert filtered[-1].get("action") == DroneManagerActions.MISSION_UPLOAD

    mission = _wait_mission_in_store(
        system_bus,
        mission_id,
        retries=10,
        delay=1.5,
        predicate=lambda mission: mission.get("assigned_drone") == drone_id and mission.get("status") == "assigned",
    )
    assert mission is not None
    assert mission.get("assigned_drone") == drone_id
    assert mission.get("status") == "assigned"


def test_task_start_updates_store_and_publishes_start(system_bus):
    """Orchestrator task_start публикует команду старта в DroneManager внутри GCS."""
    drone_id = "dr-it-2"
    corr_assign = f"corr-pre-start-{uuid4().hex[:8]}"
    corr_start = f"corr-start-{uuid4().hex[:8]}"

    planned = _submit_task_via_gateway(system_bus, _build_task_payload())
    if planned is None:
        pytest.skip("No response from gateway. Ensure GCS docker stack is up.")
    mission_id = planned.get("payload", {}).get("mission_id")
    assert mission_id

    def _publish_assign():
        system_bus.publish(
            SystemTopics.GCS,
            _gateway_publish_message(
                OrchestratorActions.TASK_ASSIGN,
                {
                    "mission_id": mission_id,
                    "drone_id": drone_id,
                },
                correlation_id=corr_assign,
            ),
        )

    assign_messages = _capture_messages_during(
        system_bus,
        DroneManagerTopics.DRONE_MANAGER,
        _publish_assign,
        expected_count=1,
        timeout=15.0,
    )
    assign_filtered = [m for m in assign_messages if m.get("correlation_id") == corr_assign]
    if not assign_filtered:
        pytest.skip("Task assign chain is not ready in current docker stack.")
    assert assign_filtered[-1].get("action") == DroneManagerActions.MISSION_UPLOAD

    mission_assigned = _wait_mission_in_store(
        system_bus,
        mission_id,
        retries=10,
        delay=1.5,
        predicate=lambda mission: mission.get("status") == "assigned",
    )
    if mission_assigned is None or mission_assigned.get("status") != "assigned":
        pytest.skip("Task assign chain is not ready in current docker stack.")

    def _publish_start():
        system_bus.publish(
            SystemTopics.GCS,
            _gateway_publish_message(
                OrchestratorActions.TASK_START,
                {
                    "mission_id": mission_id,
                    "drone_id": drone_id,
                },
                correlation_id=corr_start,
            ),
        )

    start_messages = _capture_messages_during(
        system_bus,
        DroneManagerTopics.DRONE_MANAGER,
        _publish_start,
        expected_count=1,
        timeout=15.0,
    )
    filtered = [m for m in start_messages if m.get("correlation_id") == corr_start]
    assert filtered, "Expected drone_manager start message for task_start"
    assert filtered[-1].get("action") == DroneManagerActions.MISSION_START
