import json

from sdk.security_journal import JournalRecorder
from systems.gcs.src.gateway.topics import ComponentTopics as GatewayComponentTopics
from systems.gcs.src.gateway.topics import ExternalTopics, GatewayActions
from systems.gcs.src.security_monitor.src.security_monitor import SecurityMonitorComponent
from systems.gcs.src.security_monitor.topics import SecurityMonitorActions
from systems.gcs.topics import DroneActions, DroneTopics


def _make_component(bus, tmp_path):
    journal_path = tmp_path / "gcs_security_journal.ndjson"
    journal = JournalRecorder(
        file_path=str(journal_path),
        service="GCS",
        service_id=1,
    )
    return (
        SecurityMonitorComponent(
            component_id="gcs_security_monitor",
            bus=bus,
            topic="components.gcs_security_monitor",
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


def test_proxy_request_checks_policy_and_routes_gcs_call(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)
    mock_bus.request.return_value = {"success": True, "payload": {"ok": True}}

    result = component._handle_proxy_request(
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
    mock_bus.request.assert_called_once_with(
        GatewayComponentTopics.ORCHESTRATOR,
        {
            "action": GatewayActions.TASK_SUBMIT,
            "sender": ExternalTopics.GCS,
            "payload": {"task_id": "T-1"},
        },
        timeout=10.0,
    )


def test_proxy_request_denies_when_policy_absent(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)
    component._policies = set()

    result = component._handle_proxy_request(
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
    assert result["reason"] == "policy_not_found"
    mock_bus.request.assert_not_called()
    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "critical"
    assert entry["details"]["decision"] == "denied"


def test_policy_distinguishes_request_and_publish(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)
    component._policies = {
        ("request", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_ASSIGN),
    }

    result = component._handle_proxy_publish(
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
    mock_bus.publish.assert_not_called()


def test_proxy_publish_preserves_correlation_id(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)
    mock_bus.publish.return_value = True

    result = component._handle_proxy_publish(
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
    mock_bus.publish.assert_called_once_with(
        GatewayComponentTopics.ORCHESTRATOR,
        {
            "action": GatewayActions.TASK_ASSIGN,
            "sender": ExternalTopics.GCS,
            "payload": {"mission_id": "m-1", "drone_id": "dr-1"},
            "correlation_id": "corr-1",
        },
    )


def test_proxy_publish_prefers_trace_correlation_id_from_gateway(mock_bus, tmp_path):
    component, _ = _make_component(mock_bus, tmp_path)
    mock_bus.publish.return_value = True

    result = component._handle_proxy_publish(
        {
            "sender": ExternalTopics.OPERATOR,
            "correlation_id": "internal-bus-corr",
            "trace_correlation_id": "external-corr",
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
    assert mock_bus.publish.call_args.args[1]["correlation_id"] == "external-corr"


def test_proxy_request_routes_agrodron_call(monkeypatch, mock_bus, tmp_path):
    monkeypatch.setattr(DroneTopics, "SECURITY_MONITOR", "agrodron.security_monitor")
    monkeypatch.setattr(DroneTopics, "TELEMETRY", "agrodron.telemetry")
    component, _ = _make_component(mock_bus, tmp_path)
    mock_bus.request.return_value = {
        "payload": {
            "target_response": {
                "success": True,
                "payload": {"telemetry": {"battery": 88}},
            }
        }
    }

    result = component._handle_proxy_request(
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
    mock_bus.request.assert_called_once_with(
        DroneTopics.SECURITY_MONITOR,
        {
            "action": DroneActions.PROXY_REQUEST,
            "sender": ExternalTopics.GCS,
            "payload": {
                "target": {
                    "topic": DroneTopics.TELEMETRY,
                    "action": DroneActions.TELEMETRY_GET,
                },
                "data": {"drone_id": "dr-1"},
            },
            "correlation_id": "corr-agro-1",
            "trace_correlation_id": "corr-agro-1",
        },
        timeout=10.0,
    )


def test_proxy_request_reports_missing_agrodron_security_monitor(monkeypatch, mock_bus, tmp_path):
    monkeypatch.setattr(DroneTopics, "SECURITY_MONITOR", "")
    monkeypatch.setattr(DroneTopics, "TELEMETRY", "agrodron.telemetry")
    component, _ = _make_component(mock_bus, tmp_path)

    result = component._handle_proxy_request(
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
    mock_bus.request.assert_not_called()


def test_proxy_publish_reports_missing_agrodron_security_monitor(monkeypatch, mock_bus, tmp_path):
    monkeypatch.setattr(DroneTopics, "SECURITY_MONITOR", "")
    monkeypatch.setattr(DroneTopics, "AUTOPILOT", "agrodron.autopilot")
    component, journal_path = _make_component(mock_bus, tmp_path)
    component._policies = {
        ("publish", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.CMD),
    }

    result = component._handle_proxy_publish(
        {
            "sender": ExternalTopics.GCS,
            "payload": {
                "target": {
                    "topic": ExternalTopics.AGRODRON,
                    "action": DroneActions.CMD,
                },
                "data": {"command": "START"},
            },
        }
    )

    assert result == {
        "ok": False,
        "error": "missing_route_config",
        "missing": "AGRODRON_SECURITY_MONITOR_TOPIC",
        "target_action": DroneActions.CMD,
    }
    mock_bus.publish.assert_not_called()
    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "error"
    assert entry["details"]["decision"] == "error"
    assert entry["details"]["reason"] == "missing_route_config"


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
            "sender": "components.drone_manager",
            "payload": {
                "event": "load_mission",
                "sender": "systems.gcs",
                "success": True,
                "component_id": "gcs_drone_manager",
            },
        }
    )

    entry = _read_journal(journal_path)[-1]
    assert entry["service"] == "GCS"
    assert entry["service_id"] == 1
    assert entry["severity"] == "info"
    assert entry["source_sender"] == "components.drone_manager"
    assert entry["source_component"] == "gcs_drone_manager"
    assert entry["source_action"] == "load_mission"
    assert entry["details"]["success"] is True


def test_failed_log_event_is_written_as_error(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.LOG_EVENT,
            "sender": "components.gateway",
            "payload": {
                "event": "proxy_request",
                "success": False,
                "error": "policy_denied",
                "component_id": "gcs",
            },
        }
    )

    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "error"
    assert entry["source_action"] == "proxy_request"
    assert entry["details"]["error"] == "policy_denied"


def test_security_audit_event_preserves_explicit_fields(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.SECURITY_AUDIT,
            "sender": "systems.gcs",
            "payload": {
                "severity": "critical",
                "source_component": "gateway",
                "source_action": "proxy_request.denied",
                "message": "Denied external request",
                "details": {"target_action": "cmd"},
            },
        }
    )

    entry = _read_journal(journal_path)[-1]
    assert entry["severity"] == "critical"
    assert entry["message"] == "Denied external request"
    assert entry["details"] == {"target_action": "cmd"}


def test_log_event_ignores_self_publish(mock_bus, tmp_path):
    component, journal_path = _make_component(mock_bus, tmp_path)

    component._handle_log_event(
        {
            "action": SecurityMonitorActions.LOG_EVENT,
            "sender": component.topic,
            "payload": {
                "event": "ping",
                "success": True,
                "component_id": "gcs_security_monitor",
            },
        }
    )

    assert not journal_path.exists()
