"""Gateway для внешнего взаимодействия с DronePort."""

import os
from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.base_proxy_gateway import BaseProxyGateway

from ..topics import ComponentTopics, ExternalTopics, GatewayActions, SystemTopics

PolicyKey = tuple[str, str, str, str]


class DronePortGateway(BaseProxyGateway):
    PROXY_TIMEOUT = 10.0
    PROXY_REQUEST_ACTION = GatewayActions.PROXY_REQUEST
    PROXY_PUBLISH_ACTION = GatewayActions.PROXY_PUBLISH
    LIST_POLICIES_ACTION = GatewayActions.LIST_POLICIES

    DEFAULT_POLICIES: set[PolicyKey] = {
        ("request", ExternalTopics.OPERATOR, ExternalTopics.DRONE_PORT, GatewayActions.GET_AVAILABLE_DRONES),
        ("request", ExternalTopics.AGRODRON, ExternalTopics.DRONE_PORT, GatewayActions.REQUEST_LANDING),
        ("request", ExternalTopics.AGRODRON, ExternalTopics.DRONE_PORT, GatewayActions.REQUEST_TAKEOFF),
        ("publish", ExternalTopics.DRONE_PORT, ExternalTopics.SITL, GatewayActions.SITL_HOME_PUBLISH),
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
            system_type="drone_port",
            topic=SystemTopics.DRONE_PORT,
            bus=bus,
            policies=set(policies) if policies is not None else set(self.DEFAULT_POLICIES),
            health_port=health_port,
        )

    def _route_request(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        if target_topic != ExternalTopics.DRONE_PORT:
            return None
        if target_action == GatewayActions.GET_AVAILABLE_DRONES:
            bus_topic = ComponentTopics.ORCHESTRATOR
        elif target_action in {GatewayActions.REQUEST_LANDING, GatewayActions.REQUEST_TAKEOFF}:
            bus_topic = ComponentTopics.DRONE_MANAGER
        else:
            return None
        return self.bus.request(
            bus_topic,
            {
                "action": target_action,
                "sender": self.system_id,
                "payload": data,
            },
            timeout=self.PROXY_TIMEOUT,
        )

    def _route_publish(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> bool:
        if target_topic == ExternalTopics.SITL and target_action == GatewayActions.SITL_HOME_PUBLISH:
            topic = (os.environ.get("SITL_HOME_TOPIC") or "").strip() or ExternalTopics.SITL
            return self.bus.publish(topic, dict(data))
        return False
