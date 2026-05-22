import json

from sdk.security_journal import JournalRecorder
from systems.drone_port.src.gateway.topics import ComponentTopics as GatewayComponentTopics
from systems.drone_port.src.gateway.topics import ExternalTopics, GatewayActions
from systems.drone_port.src.security_monitor.src.security_monitor import SecurityMonitorComponent
from systems.drone_port.src.security_monitor.topics import SecurityMonitorActions


def _make_component(bus, tmp_path):
    journal_path = tmp_path / "drone_port_security_journal.ndjson"
    journal = JournalRecorder(
        file_path=str(journal_path),
        service="DronePort",
        service_id=2,
    )
    return (
        SecurityMonitorComponent(
            component_id="drone_port_security_monitor",
            bus=bus,
            topic="components.drone_port_security_monitor",
            journal=journal,
        ),
        journal_path,
    )


def _read_journal(path):
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line
    ]


def test_registers_security_journal_handlers(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)

    assert SecurityMonitorActions.LOG_EVENT in component._handlers
    assert SecurityMonitorActions.SECURITY_AUDIT in component._handlers
    assert GatewayActions.PROXY_REQUEST in component._handlers
    assert GatewayActions.PROXY_PUBLISH in component._handlers
    assert GatewayActions.LIST_POLICIES in component._handlers


def test_proxy_request_checks_policy_and_routes_to_drone_manager(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)
    mock_bus.request.return_value = {"approved": True, "port_id": "P-01"}

    result = component._handle_proxy_request(
        {
            "sender": ExternalTopics.AGRODRON,
            "payload": {
                "target": {
                    "topic": ExternalTopics.DRONE_PORT,
                    "action": GatewayActions.REQUEST_LANDING,
                },
                "data": {"drone_id": "DR-1"},
            },
        }
    )

    assert result == {"target_response": {"approved": True, "port_id": "P-01"}}
    mock_bus.request.assert_called_once_with(
        GatewayComponentTopics.DRONE_MANAGER,
        {
            "action": GatewayActions.REQUEST_LANDING,
            "sender": ExternalTopics.DRONE_PORT,
            "payload": {"drone_id": "DR-1"},
        },
        timeout=10.0,
    )


def test_proxy_request_denies_when_policy_absent(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)
    component._policies = set()

    result = component._handle_proxy_request(
        {
            "sender": ExternalTopics.AGRODRON,
            "payload": {
                "target": {
                    "topic": ExternalTopics.DRONE_PORT,
                    "action": GatewayActions.REQUEST_LANDING,
                },
                "data": {"drone_id": "DR-1"},
            },
        }
    )

    assert result["error"] == "policy_denied"
    mock_bus.request.assert_not_called()
    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "critical"
    assert entry["details"]["decision"] == "denied"


def test_proxy_publish_routes_to_sitl(monkeypatch, mock_bus, tmp_path):
    monkeypatch.setenv("SITL_HOME_TOPIC", "sitl")
    component, _ = _make_component(mock_bus, tmp_path)
    mock_bus.publish.return_value = True

    result = component._handle_proxy_publish(
        {
            "sender": ExternalTopics.DRONE_PORT,
            "payload": {
                "target": {
                    "topic": ExternalTopics.SITL,
                    "action": GatewayActions.SITL_HOME_PUBLISH,
                },
                "data": {"drone_id": "DR-1", "home_lat": 1.0, "home_lon": 2.0, "home_alt": 3.0},
            },
        }
    )

    assert result == {"published": True}
    mock_bus.publish.assert_called_once_with(
        "sitl",
        {"drone_id": "DR-1", "home_lat": 1.0, "home_lon": 2.0, "home_alt": 3.0},
    )


def test_list_policies_requires_read_policy(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)
    component._policies = set()

    result = component._handle_list_policies(
        {
            "sender": ExternalTopics.OPERATOR,
            "payload": {},
        }
    )

    assert result["error"] == "policy_denied"
    assert result["target_action"] == GatewayActions.LIST_POLICIES
    entry = _read_journal(journal_path)[-1]
    assert entry["details"]["mode"] == "read"
    assert entry["details"]["decision"] == "denied"


def test_list_policies_allowed_by_read_policy(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)

    result = component._handle_list_policies(
        {
            "sender": ExternalTopics.OPERATOR,
            "payload": {},
        }
    )

    assert result["count"] == len(component._policies)
    assert {
        "mode": "read",
        "sender": ExternalTopics.OPERATOR,
        "topic": component.topic,
        "action": GatewayActions.LIST_POLICIES,
    } in result["policies"]


def test_log_event_from_base_component_is_written_to_journal(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.LOG_EVENT,
            "sender": "components.port_manager",
            "payload": {
                "event": "request_landing",
                "sender": "systems.agrodron",
                "success": True,
                "component_id": "port_manager",
            },
        }
    )

    entry = _read_journal(journal_path)[-1]
    assert entry["service"] == "DronePort"
    assert entry["service_id"] == 2
    assert entry["severity"] == "info"
    assert entry["source_sender"] == "components.port_manager"
    assert entry["source_component"] == "port_manager"
    assert entry["source_action"] == "request_landing"
    assert entry["details"]["success"] is True


def test_failed_log_event_is_written_as_error(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.LOG_EVENT,
            "sender": "systems.drone_port",
            "payload": {
                "event": "proxy_publish",
                "success": False,
                "error": "missing_route_config",
                "component_id": "drone_port",
            },
        }
    )

    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "error"
    assert entry["source_action"] == "proxy_publish"
    assert entry["details"]["error"] == "missing_route_config"


def test_security_audit_event_preserves_explicit_fields(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.SECURITY_AUDIT,
            "sender": "systems.drone_port",
            "payload": {
                "severity": "warning",
                "source_component": "gateway",
                "source_action": "sitl_home_publish.invalid",
                "message": "Invalid SITL publish",
                "details": {"target_action": "sitl_home_publish"},
            },
        }
    )

    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "warning"
    assert entry["message"] == "Invalid SITL publish"
    assert entry["details"] == {"target_action": "sitl_home_publish"}


def test_log_event_ignores_self_publish(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.LOG_EVENT,
            "sender": component.topic,
            "payload": {
                "event": "ping",
                "success": True,
                "component_id": "drone_port_security_monitor",
            },
        }
    )

    assert not journal_path.exists()
