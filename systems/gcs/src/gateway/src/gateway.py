"""Gateway для внешнего взаимодействия с GCS."""

from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.base_proxy_gateway import BaseProxyGateway

from ....topics import DroneActions, DroneTopics
from ..topics import ComponentTopics, ExternalTopics, GatewayActions, SystemTopics

PolicyKey = tuple[str, str, str, str]


class GCSGateway(BaseProxyGateway):
    PROXY_TIMEOUT = 10.0
    PROXY_REQUEST_ACTION = GatewayActions.PROXY_REQUEST
    PROXY_PUBLISH_ACTION = GatewayActions.PROXY_PUBLISH
    LIST_POLICIES_ACTION = GatewayActions.LIST_POLICIES

    DEFAULT_POLICIES: set[PolicyKey] = {
        ("request", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_SUBMIT),
        ("publish", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_ASSIGN),
        ("publish", ExternalTopics.OPERATOR, ExternalTopics.GCS, GatewayActions.TASK_START),
        ("request", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.LOAD_MISSION),
        ("request", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.CMD),
        ("request", ExternalTopics.GCS, ExternalTopics.AGRODRON, DroneActions.TELEMETRY_GET),
    }

    def __init__(
        self,
        system_id: str,
        bus: SystemBus,
        health_port: Optional[int] = None,
        policies: Optional[set[PolicyKey]] = None,
    ):
        super().__init__(
            system_id=system_id,
            system_type="gcs",
            topic=SystemTopics.GCS,
            bus=bus,
            policies=set(policies) if policies is not None else set(self.DEFAULT_POLICIES),
            health_port=health_port,
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
            "sender": self.topic,
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
            return self.bus.request(
                ComponentTopics.ORCHESTRATOR,
                {
                    "action": target_action,
                    "sender": self.system_id,
                    "payload": data,
                },
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
    ) -> bool:
        if target_topic != ExternalTopics.AGRODRON:
            if target_topic == ExternalTopics.GCS:
                message = {
                    "action": target_action,
                    "sender": self.system_id,
                    "payload": data,
                }
                if correlation_id:
                    message["correlation_id"] = correlation_id
                return self.bus.publish(
                    ComponentTopics.ORCHESTRATOR,
                    message,
                )
            return False
        target_component_topic = {
            DroneActions.LOAD_MISSION: DroneTopics.MISSION_HANDLER,
            DroneActions.CMD: DroneTopics.AUTOPILOT,
            DroneActions.TELEMETRY_GET: DroneTopics.TELEMETRY,
        }.get(target_action)
        if not target_component_topic:
            return False
        message = {
            "action": DroneActions.PROXY_PUBLISH,
            "sender": self.topic,
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
