from unittest.mock import MagicMock

from ...src.gateway.src.gateway import GCSGateway
from ...src.gateway.topics import ExternalTopics, GatewayActions
from ...src.security_monitor.topics import ComponentTopics as SecurityMonitorTopics


def test_gateway_registers_only_proxy_handlers():
    gateway = GCSGateway(system_id="gcs", bus=MagicMock())

    assert GatewayActions.TASK_SUBMIT not in gateway._handlers
    assert GatewayActions.TASK_ASSIGN not in gateway._handlers
    assert GatewayActions.TASK_START not in gateway._handlers
    assert GatewayActions.PROXY_REQUEST in gateway._handlers
    assert GatewayActions.PROXY_PUBLISH in gateway._handlers
    assert GatewayActions.LIST_POLICIES in gateway._handlers


def test_gateway_proxy_request_delegates_to_security_monitor():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    message = {
        "action": GatewayActions.PROXY_REQUEST,
        "sender": ExternalTopics.OPERATOR,
        "correlation_id": "corr-1",
        "payload": {
            "target": {
                "topic": ExternalTopics.GCS,
                "action": GatewayActions.TASK_SUBMIT,
            },
            "data": {"task_id": "T-1"},
        },
    }
    bus.request.return_value = {
        "payload": {
            "target_response": {"success": True, "payload": {"ok": True}},
        }
    }

    result = gateway._handle_proxy_request(message)

    assert result == {"target_response": {"success": True, "payload": {"ok": True}}}
    bus.request.assert_called_once_with(
        SecurityMonitorTopics.SECURITY_MONITOR,
        {
            **message,
            "trace_correlation_id": "corr-1",
        },
        timeout=10.0,
    )


def test_gateway_proxy_publish_delegates_to_security_monitor():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    message = {
        "action": GatewayActions.PROXY_PUBLISH,
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
    bus.request.return_value = {"payload": {"published": True}}

    result = gateway._handle_proxy_publish(message)

    assert result == {"published": True}
    bus.request.assert_called_once_with(
        SecurityMonitorTopics.SECURITY_MONITOR,
        {
            **message,
            "trace_correlation_id": "corr-1",
        },
        timeout=10.0,
    )


def test_gateway_list_policies_delegates_to_security_monitor():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    message = {"action": GatewayActions.LIST_POLICIES, "sender": ExternalTopics.OPERATOR, "payload": {}}
    bus.request.return_value = {"payload": {"count": 1, "policies": [{"mode": "request"}]}}

    result = gateway._handle_list_policies(message)

    assert result == {"count": 1, "policies": [{"mode": "request"}]}
    bus.request.assert_called_once_with(
        SecurityMonitorTopics.SECURITY_MONITOR,
        message,
        timeout=10.0,
    )


def test_gateway_list_policies_preserves_trace_correlation_id():
    bus = MagicMock()
    gateway = GCSGateway(system_id="gcs", bus=bus)
    message = {
        "action": GatewayActions.LIST_POLICIES,
        "sender": ExternalTopics.OPERATOR,
        "correlation_id": "corr-list-1",
        "payload": {},
    }
    bus.request.return_value = {"payload": {"count": 0, "policies": []}}

    result = gateway._handle_list_policies(message)

    assert result == {"count": 0, "policies": []}
    bus.request.assert_called_once_with(
        SecurityMonitorTopics.SECURITY_MONITOR,
        {
            **message,
            "trace_correlation_id": "corr-list-1",
        },
        timeout=10.0,
    )
