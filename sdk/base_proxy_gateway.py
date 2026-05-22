"""BaseProxyGateway — gateway with explicit policy-checked proxy actions."""

from abc import abstractmethod
from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.base_system import BaseSystem

PolicyKey = tuple[str, str, str, str]


class BaseProxyGateway(BaseSystem):
    """Base class for system gateways that only expose proxy_request/proxy_publish."""

    PROXY_TIMEOUT: float = 10.0
    PROXY_REQUEST_ACTION = "proxy_request"
    PROXY_PUBLISH_ACTION = "proxy_publish"
    LIST_POLICIES_ACTION = "list_policies"

    def __init__(
        self,
        system_id: str,
        system_type: str,
        topic: str,
        bus: SystemBus,
        policies: Optional[set[PolicyKey]] = None,
        health_port: Optional[int] = None,
    ):
        self._policies = set(policies or set())
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

    def _extract_target(self, payload: Dict[str, Any]) -> Optional[tuple[str, str, Dict[str, Any]]]:
        target = payload.get("target") or {}
        target_topic = str(target.get("topic", "")).strip()
        target_action = str(target.get("action", "")).strip()
        target_payload = payload.get("data", {})
        if not target_topic or not target_action or not isinstance(target_payload, dict):
            return None
        return target_topic, target_action, target_payload

    def _is_allowed(self, mode: str, sender_id: str, target_topic: str, target_action: str) -> bool:
        return (mode, sender_id, target_topic, target_action) in self._policies

    def _deny(self, reason: str, sender_id: str, target_topic: str = "", target_action: str = "") -> Dict[str, Any]:
        return {
            "ok": False,
            "error": "policy_denied",
            "reason": reason,
            "sender": sender_id,
            "target_topic": target_topic,
            "target_action": target_action,
        }

    @abstractmethod
    def _route_request(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> Optional[Dict[str, Any]]:
        pass

    @abstractmethod
    def _route_publish(
        self,
        target_topic: str,
        target_action: str,
        data: Dict[str, Any],
        correlation_id: str | None = None,
    ) -> bool:
        pass

    def _handle_proxy_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        sender_id = str(message.get("sender") or "").strip()
        target = self._extract_target(payload)
        if not sender_id or target is None:
            return self._deny("invalid_target_or_sender", sender_id or "unknown")

        target_topic, target_action, target_payload = target
        if not self._is_allowed("request", sender_id, target_topic, target_action):
            return self._deny("policy_not_found", sender_id, target_topic, target_action)

        correlation_id = message.get("correlation_id")
        response = self._route_request(
            target_topic,
            target_action,
            target_payload,
            correlation_id=str(correlation_id) if correlation_id else None,
        )
        if not isinstance(response, dict):
            return {"ok": False, "error": "no_response", "target_topic": target_topic, "target_action": target_action}

        return {"target_response": response}

    def _handle_proxy_publish(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        sender_id = str(message.get("sender") or "").strip()
        target = self._extract_target(payload)
        if not sender_id or target is None:
            return self._deny("invalid_target_or_sender", sender_id or "unknown")

        target_topic, target_action, target_payload = target
        if not self._is_allowed("publish", sender_id, target_topic, target_action):
            return self._deny("policy_not_found", sender_id, target_topic, target_action)

        correlation_id = message.get("correlation_id")
        return {
            "published": bool(
                self._route_publish(
                    target_topic,
                    target_action,
                    target_payload,
                    correlation_id=str(correlation_id) if correlation_id else None,
                )
            )
        }

    def _handle_list_policies(self, message: Dict[str, Any]) -> Dict[str, Any]:
        policies = [
            {"mode": mode, "sender": sender, "topic": topic, "action": action}
            for mode, sender, topic, action in sorted(self._policies)
        ]
        return {"count": len(policies), "policies": policies}
