"""DronePort security monitor journal component."""

from __future__ import annotations

import logging
import os
from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.security_journal import InfopanelDispatcher, JournalRecorder
from sdk.security_policy_monitor import PolicyKey, SecurityPolicyMonitor
from systems.drone_port.src.gateway.topics import ComponentTopics as GatewayComponentTopics
from systems.drone_port.src.gateway.topics import ExternalTopics, GatewayActions, SystemTopics
from systems.drone_port.src.security_monitor import config
from systems.drone_port.src.security_monitor.topics import ComponentTopics as SecurityMonitorTopics


logger = logging.getLogger(__name__)


class SecurityMonitorComponent(SecurityPolicyMonitor):
    PROXY_REQUEST_ACTION = GatewayActions.PROXY_REQUEST
    PROXY_PUBLISH_ACTION = GatewayActions.PROXY_PUBLISH
    LIST_POLICIES_ACTION = GatewayActions.LIST_POLICIES

    DEFAULT_POLICIES: set[PolicyKey] = {
        ("request", ExternalTopics.OPERATOR, ExternalTopics.DRONE_PORT, GatewayActions.GET_AVAILABLE_DRONES),
        ("request", ExternalTopics.AGRODRON, ExternalTopics.DRONE_PORT, GatewayActions.REQUEST_LANDING),
        ("request", ExternalTopics.AGRODRON, ExternalTopics.DRONE_PORT, GatewayActions.REQUEST_TAKEOFF),
        ("publish", ExternalTopics.DRONE_PORT, ExternalTopics.SITL, GatewayActions.SITL_HOME_PUBLISH),
        ("read", ExternalTopics.OPERATOR, SecurityMonitorTopics.SECURITY_MONITOR, GatewayActions.LIST_POLICIES),
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
            component_type="drone_port_security_monitor",
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
            bus_topic = GatewayComponentTopics.ORCHESTRATOR
        elif target_action in {GatewayActions.REQUEST_LANDING, GatewayActions.REQUEST_TAKEOFF}:
            bus_topic = GatewayComponentTopics.DRONE_MANAGER
        else:
            return None
        message = {
            "action": target_action,
            "sender": SystemTopics.DRONE_PORT,
            "payload": data,
        }
        if correlation_id:
            message["correlation_id"] = correlation_id
        return self.bus.request(bus_topic, message, timeout=self.PROXY_TIMEOUT)

    def _route_publish(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> bool | Dict[str, Any]:
        if target_topic == ExternalTopics.SITL and target_action == GatewayActions.SITL_HOME_PUBLISH:
            topic = (os.environ.get("SITL_HOME_TOPIC") or "").strip() or ExternalTopics.SITL
            return self.bus.publish(topic, dict(data))
        return False
