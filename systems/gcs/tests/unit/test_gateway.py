from unittest.mock import MagicMock

from ...src.gateway.src.gateway import GCSGateway
from ...src.gateway.topics import ExternalTopics, GatewayActions
from ...src.orchestrator.topics import ComponentTopics
from ...topics import DroneActions, DroneTopics


def test_gateway_registers_only_proxy_handlers():
    gateway = GCSGateway(system_id="gcs", bus=MagicMock())

    assert GatewayActions.TASK_SUBMIT not in gateway._handlers
    assert GatewayActions.TASK_ASSIGN not in gateway._handlers
    assert GatewayActions.TASK_START not in gateway._handlers
    assert GatewayActions.PROXY_REQUEST in gateway._handlers
    assert GatewayActions.PROXY_PUBLISH in gateway._handlers
    assert GatewayActions.LIST_POLICIES in gateway._handlers


def test_gateway_proxy_request_checks_policy_and_routes_gcs_call():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    bus.request.return_value = {"success": True, "payload": {"ok": True}}

    result = gateway._handle_proxy_request(
        {
            "action": GatewayActions.PROXY_REQUEST,
            "sender": ExternalTopics.OPERATOR,
            "payload": {
                "target": {
                    "topic": ExternalTopics.GCS,
                    "action": GatewayActions.TASK_SUBMIT,
                },
                "data": {"task_id": "T-1"},
            },
        }
    )

    assert result == {"target_response": {"success": True, "payload": {"ok": True}}}
    bus.request.assert_called_once_with(
        ComponentTopics.ORCHESTRATOR,
        {
            "action": GatewayActions.TASK_SUBMIT,
            "sender": "gcs",
            "payload": {"task_id": "T-1"},
        },
        timeout=10.0,
    )


def test_gateway_proxy_request_denies_when_policy_absent():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus, policies=set())

    result = gateway._handle_proxy_request(
        {
            "sender": ExternalTopics.OPERATOR,
            "payload": {
                "target": {
                    "topic": ExternalTopics.GCS,
                    "action": GatewayActions.TASK_SUBMIT,
                },
                "data": {},
            },
        }
    )

    assert result["error"] == "policy_denied"
    bus.request.assert_not_called()


def test_gateway_policy_distinguishes_request_and_publish():
    bus = MagicMock()
    gateway = GCSGateway(
        system_id="gcs",
        bus=bus,
        policies={
            ("request", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_ASSIGN),
        },
    )

    result = gateway._handle_proxy_publish(
        {
            "sender": ExternalTopics.OPERATOR,
            "payload": {
                "target": {
                    "topic": ExternalTopics.GCS,
                    "action": GatewayActions.TASK_ASSIGN,
                },
                "data": {"mission_id": "m-1", "drone_id": "dr-1"},
            },
        }
    )

    assert result["error"] == "policy_denied"
    bus.publish.assert_not_called()


def test_gateway_proxy_publish_preserves_correlation_id():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    bus.publish.return_value = True

    result = gateway._handle_proxy_publish(
        {
            "sender": ExternalTopics.OPERATOR,
            "correlation_id": "corr-1",
            "payload": {
                "target": {
                    "topic": ExternalTopics.GCS,
                    "action": GatewayActions.TASK_ASSIGN,
                },
                "data": {"mission_id": "m-1", "drone_id": "dr-1"},
            },
        }
    )

    assert result == {"published": True}
    bus.publish.assert_called_once_with(
        ComponentTopics.ORCHESTRATOR,
        {
            "action": GatewayActions.TASK_ASSIGN,
            "sender": "gcs",
            "payload": {"mission_id": "m-1", "drone_id": "dr-1"},
            "correlation_id": "corr-1",
        },
    )


def test_gateway_proxy_request_routes_agrodron_call(monkeypatch):
    monkeypatch.setattr(DroneTopics, "SECURITY_MONITOR", "agrodron.security_monitor")
    monkeypatch.setattr(DroneTopics, "TELEMETRY", "agrodron.telemetry")
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    bus.request.return_value = {
        "payload": {
            "target_response": {
                "success": True,
                "payload": {"telemetry": {"battery": 88}},
            }
        }
    }

    result = gateway._handle_proxy_request(
        {
            "sender": ExternalTopics.GCS,
            "correlation_id": "corr-agro-1",
            "payload": {
                "target": {
                    "topic": ExternalTopics.AGRODRON,
                    "action": DroneActions.TELEMETRY_GET,
                },
                "data": {"drone_id": "dr-1"},
            },
        }
    )

    assert result == {"target_response": {"success": True, "payload": {"telemetry": {"battery": 88}}}}
    bus.request.assert_called_once_with(
        DroneTopics.SECURITY_MONITOR,
        {
            "action": DroneActions.PROXY_REQUEST,
            "sender": gateway.topic,
            "payload": {
                "target": {
                    "topic": DroneTopics.TELEMETRY,
                    "action": DroneActions.TELEMETRY_GET,
                },
                "data": {"drone_id": "dr-1"},
            },
            "correlation_id": "corr-agro-1",
        },
        timeout=10.0,
    )


def test_gateway_proxy_request_reports_missing_agrodron_security_monitor(monkeypatch):
    monkeypatch.setattr(DroneTopics, "SECURITY_MONITOR", "")
    monkeypatch.setattr(DroneTopics, "TELEMETRY", "agrodron.telemetry")
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)

    result = gateway._handle_proxy_request(
        {
            "sender": ExternalTopics.GCS,
            "payload": {
                "target": {
                    "topic": ExternalTopics.AGRODRON,
                    "action": DroneActions.TELEMETRY_GET,
                },
                "data": {"drone_id": "dr-1"},
            },
        }
    )

    assert result == {
        "target_response": {
            "ok": False,
            "error": "missing_route_config",
            "missing": "AGRODRON_SECURITY_MONITOR_TOPIC",
            "target_action": DroneActions.TELEMETRY_GET,
        }
    }
    bus.request.assert_not_called()


def test_gateway_proxy_request_reports_missing_agrodron_target_topic(monkeypatch):
    monkeypatch.setattr(DroneTopics, "SECURITY_MONITOR", "agrodron.security_monitor")
    monkeypatch.setattr(DroneTopics, "TELEMETRY", "")
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)

    result = gateway._handle_proxy_request(
        {
            "sender": ExternalTopics.GCS,
            "payload": {
                "target": {
                    "topic": ExternalTopics.AGRODRON,
                    "action": DroneActions.TELEMETRY_GET,
                },
                "data": {"drone_id": "dr-1"},
            },
        }
    )

    assert result == {
        "target_response": {
            "ok": False,
            "error": "missing_route_config",
            "missing": "AGRODRON_TELEMETRY_TOPIC",
            "target_action": DroneActions.TELEMETRY_GET,
        }
    }
    bus.request.assert_not_called()
