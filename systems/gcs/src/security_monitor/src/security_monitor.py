"""GCS security monitor journal component."""

from __future__ import annotations

import logging
from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.security_journal import InfopanelDispatcher, JournalRecorder
from sdk.security_policy_monitor import PolicyKey, SecurityPolicyMonitor
from systems.gcs.src.gateway.topics import ComponentTopics as GatewayComponentTopics
from systems.gcs.src.gateway.topics import ExternalTopics, GatewayActions, SystemTopics
from systems.gcs.src.security_monitor import config
from systems.gcs.src.security_monitor.topics import ComponentTopics as SecurityMonitorTopics
from systems.gcs.topics import DroneActions, DroneTopics


logger = logging.getLogger(__name__)


class SecurityMonitorComponent(SecurityPolicyMonitor):
    PROXY_REQUEST_ACTION = GatewayActions.PROXY_REQUEST
    PROXY_PUBLISH_ACTION = GatewayActions.PROXY_PUBLISH
    LIST_POLICIES_ACTION = GatewayActions.LIST_POLICIES

    DEFAULT_POLICIES: set[PolicyKey] = {
        ("request", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_SUBMIT),
        ("publish", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_ASSIGN),
        ("publish", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_START),
        ("read", ExternalTopics.OPERATOR, SecurityMonitorTopics.SECURITY_MONITOR, GatewayActions.LIST_POLICIES),
        ("request", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.LOAD_MISSION),
        ("request", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.CMD),
        ("request", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.TELEMETRY_GET),
    }

    def __init__(
        self,
        *,
        component_id: str,
        bus: SystemBus,
        topic: str = "",
        journal: Optional[JournalRecorder] = None,
        dispatcher: Optional[InfopanelDispatcher] = None,
        policies: Optional[set[PolicyKey]] = None,
    ):
        if dispatcher is None and journal is None:
            dispatcher = InfopanelDispatcher(
                url=config.infopanel_url(),
                api_key=config.infopanel_api_key(),
                batch_size=config.infopanel_batch_size(),
                flush_interval_s=config.infopanel_flush_interval_s(),
                max_retries=config.infopanel_max_retries(),
                verify_tls=config.infopanel_verify_tls(),
                logger=logger,
            )
        super().__init__(
            component_id=component_id,
            component_type="gcs_security_monitor",
            topic=topic or config.component_topic(),
            bus=bus,
            journal=journal or JournalRecorder(
                file_path=config.journal_file_path(),
                min_severity=config.journal_min_severity(),
                service=config.service_name(),
                service_id=config.service_id(),
                logger=logger,
                sink=dispatcher,
            ),
            dispatcher=dispatcher,
            policies=set(policies) if policies is not None else set(self.DEFAULT_POLICIES),
        )

    def _unwrap_target_response(self, response: Dict[str, Any] | None) -> Dict[str, Any] | None:
        if not isinstance(response, dict):
            return None
        target_response = response.get("target_response")
        if isinstance(target_response, dict):
            return target_response
        payload = response.get("payload")
        if isinstance(payload, dict) and isinstance(payload.get("target_response"), dict):
            return payload["target_response"]
        return response

    def _route_agrodron_request(
        self,
        action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        route_topics = {
            DroneActions.LOAD_MISSION: DroneTopics.MISSION_HANDLER,
            DroneActions.CMD: DroneTopics.AUTOPILOT,
            DroneActions.TELEMETRY_GET: DroneTopics.TELEMETRY,
        }
        if action not in route_topics:
            return None
        target_topic = route_topics.get(action)
        if not DroneTopics.SECURITY_MONITOR:
            return {
                "ok": False,
                "error": "missing_route_config",
                "missing": "AGRODRON_SECURITY_MONITOR_TOPIC",
                "target_action": action,
            }
        if not target_topic:
            return {
                "ok": False,
                "error": "missing_route_config",
                "missing": {
                    DroneActions.LOAD_MISSION: "AGRODRON_MISSION_HANDLER_TOPIC",
                    DroneActions.CMD: "AGRODRON_AUTOPILOT_TOPIC",
                    DroneActions.TELEMETRY_GET: "AGRODRON_TELEMETRY_TOPIC",
                }.get(action, "agrodron_target_topic"),
                "target_action": action,
            }

        message = {
            "action": DroneActions.PROXY_REQUEST,
            "sender": SystemTopics.GCS,
            "payload": {
                "target": {
                    "topic": target_topic,
                    "action": action,
                },
                "data": data,
            },
        }
        if correlation_id:
            message["correlation_id"] = correlation_id
            message["trace_correlation_id"] = correlation_id

        response = self.bus.request(
            DroneTopics.SECURITY_MONITOR,
            message,
            timeout=self.PROXY_TIMEOUT,
        )
        return self._unwrap_target_response(response)

    def _route_request(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        if target_topic == ExternalTopics.GCS:
            message = {
                "action": target_action,
                "sender": SystemTopics.GCS,
                "payload": data,
            }
            if correlation_id:
                message["correlation_id"] = correlation_id
            return self.bus.request(
                GatewayComponentTopics.ORCHESTRATOR,
                message,
                timeout=self.PROXY_TIMEOUT,
            )
        if target_topic == ExternalTopics.AGRODRON:
            return self._route_agrodron_request(target_action, data, correlation_id=correlation_id)
        return None

    def _route_publish(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> bool | Dict[str, Any]:
        if target_topic == ExternalTopics.GCS:
            message = {
                "action": target_action,
                "sender": SystemTopics.GCS,
                "payload": data,
            }
            if correlation_id:
                message["correlation_id"] = correlation_id
            return self.bus.publish(GatewayComponentTopics.ORCHESTRATOR, message)

        if target_topic != ExternalTopics.AGRODRON:
            return False
        target_component_topic = {
            DroneActions.LOAD_MISSION: DroneTopics.MISSION_HANDLER,
            DroneActions.CMD: DroneTopics.AUTOPILOT,
            DroneActions.TELEMETRY_GET: DroneTopics.TELEMETRY,
        }.get(target_action)
        if not DroneTopics.SECURITY_MONITOR:
            return {
                "ok": False,
                "error": "missing_route_config",
                "missing": "AGRODRON_SECURITY_MONITOR_TOPIC",
                "target_action": target_action,
            }
        if not target_component_topic:
            return {
                "ok": False,
                "error": "missing_route_config",
                "missing": {
                    DroneActions.LOAD_MISSION: "AGRODRON_MISSION_HANDLER_TOPIC",
                    DroneActions.CMD: "AGRODRON_AUTOPILOT_TOPIC",
                    DroneActions.TELEMETRY_GET: "AGRODRON_TELEMETRY_TOPIC",
                }.get(target_action, "agrodron_target_topic"),
                "target_action": target_action,
            }
        message = {
            "action": DroneActions.PROXY_PUBLISH,
            "sender": SystemTopics.GCS,
            "payload": {
                "target": {
                    "topic": target_component_topic,
                    "action": target_action,
                },
                "data": data,
            },
        }
        if correlation_id:
            message["correlation_id"] = correlation_id
        return self.bus.publish(DroneTopics.SECURITY_MONITOR, message)
