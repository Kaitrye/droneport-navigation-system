"""BaseProxyGateway — thin gateway that forwards proxy actions to a security monitor."""

from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.base_system import BaseSystem


class BaseProxyGateway(BaseSystem):
    """Base class for gateways that expose proxy actions and delegate policy to SKIB monitor."""

    PROXY_TIMEOUT: float = 10.0
    PROXY_REQUEST_ACTION = "proxy_request"
    PROXY_PUBLISH_ACTION = "proxy_publish"
    LIST_POLICIES_ACTION = "list_policies"

    def __init__(
        self,
        system_id: str,
        system_type: str,
        topic: str,
        security_monitor_topic: str,
        bus: SystemBus,
        health_port: Optional[int] = None,
    ):
        self.security_monitor_topic = security_monitor_topic
        super().__init__(
            system_id=system_id,
            system_type=system_type,
            topic=topic,
            bus=bus,
            health_port=health_port,
        )

    def _register_handlers(self):
        self.register_handler(self.PROXY_REQUEST_ACTION, self._handle_proxy_request)
        self.register_handler(self.PROXY_PUBLISH_ACTION, self._handle_proxy_publish)
        self.register_handler(self.LIST_POLICIES_ACTION, self._handle_list_policies)

    def _monitor_request(self, message: Dict[str, object]) -> Optional[Dict[str, object]]:
        if not self.security_monitor_topic:
            return {
                "ok": False,
                "error": "missing_route_config",
                "missing": "SECURITY_MONITOR_TOPIC",
            }
        forwarded = dict(message)
        original_correlation_id = message.get("correlation_id")
        if original_correlation_id:
            forwarded["trace_correlation_id"] = original_correlation_id
        response = self.bus.request(
            self.security_monitor_topic,
            forwarded,
            timeout=self.PROXY_TIMEOUT,
        )
        if isinstance(response, dict):
            payload = response.get("payload")
            if isinstance(payload, dict):
                return payload
            return response
        return None

    def _handle_proxy_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        response = self._monitor_request(message)
        if isinstance(response, dict):
            return response
        return {"ok": False, "error": "no_response"}

    def _handle_proxy_publish(self, message: Dict[str, Any]) -> Dict[str, Any]:
        response = self._monitor_request(message)
        if isinstance(response, dict):
            return response
        return {"ok": False, "error": "no_response"}

    def _handle_list_policies(self, message: Dict[str, Any]) -> Dict[str, Any]:
        response = self._monitor_request(message)
        if isinstance(response, dict):
            return response
        return {"count": 0, "policies": []}
