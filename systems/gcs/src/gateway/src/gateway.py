"""Gateway для внешнего взаимодействия с GCS."""

from typing import Optional

from broker.system_bus import SystemBus
from sdk.base_proxy_gateway import BaseProxyGateway

from ...security_monitor.topics import ComponentTopics as SecurityMonitorTopics
from ..topics import GatewayActions, SystemTopics


class GCSGateway(BaseProxyGateway):
    PROXY_TIMEOUT = 10.0
    PROXY_REQUEST_ACTION = GatewayActions.PROXY_REQUEST
    PROXY_PUBLISH_ACTION = GatewayActions.PROXY_PUBLISH
    LIST_POLICIES_ACTION = GatewayActions.LIST_POLICIES

    def __init__(
        self,
        system_id: str,
        bus: SystemBus,
        health_port: Optional[int] = None,
    ):
        super().__init__(
            system_id=system_id,
            system_type="gcs",
            topic=SystemTopics.GCS,
            security_monitor_topic=SecurityMonitorTopics.SECURITY_MONITOR,
            bus=bus,
            health_port=health_port,
        )
