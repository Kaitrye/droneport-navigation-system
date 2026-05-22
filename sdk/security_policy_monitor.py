"""Policy-enforcing security monitor for gateway proxy traffic."""

from __future__ import annotations

from abc import abstractmethod
from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from sdk.base_component import BaseComponent
from sdk.security_journal import InfopanelDispatcher, JournalRecorder, LOG_EVENT_ACTION


PolicyKey = tuple[str, str, str, str]
SECURITY_AUDIT_ACTION = "security_audit"


class SecurityJournalMonitor(BaseComponent):
    """Collects log_event/security_audit messages and records them."""

    def __init__(
        self,
        *,
        component_id: str,
        component_type: str,
        topic: str,
        bus: SystemBus,
        journal: JournalRecorder,
        dispatcher: Optional[InfopanelDispatcher] = None,
    ):
        self._journal = journal
        self._dispatcher = dispatcher
        super().__init__(
            component_id=component_id,
            component_type=component_type,
            topic=topic,
            bus=bus,
        )

    def start(self):
        if self._dispatcher is not None:
            self._dispatcher.start()
        super().start()

    def stop(self):
        super().stop()
        if self._dispatcher is not None:
            self._dispatcher.stop()

    def _register_handlers(self):
        self.register_handler(LOG_EVENT_ACTION, self._handle_log_event)
        self.register_handler(SECURITY_AUDIT_ACTION, self._handle_log_event)

    def _severity_for_payload(self, payload: Dict[str, Any]) -> str:
        severity = str(payload.get("severity") or "").strip().lower()
        if severity:
            return severity
        if payload.get("error"):
            return "error"
        return "info" if payload.get("success", True) else "error"

    def _details_for_payload(self, payload: Dict[str, Any]) -> Dict[str, Any]:
        details = payload.get("details")
        if isinstance(details, dict):
            return dict(details)
        return {
            key: value
            for key, value in payload.items()
            if key not in {"severity", "message", "source_component", "source_action"}
        }

    def _handle_log_event(self, message: Dict[str, Any]) -> None:
        payload = message.get("payload") or {}
        if not isinstance(payload, dict):
            payload = {}

        sender = str(message.get("sender") or "").strip()
        if sender == self.topic:
            return None

        source_action = str(
            payload.get("source_action")
            or payload.get("event")
            or message.get("action")
            or LOG_EVENT_ACTION
        ).strip()
        source_component = str(
            payload.get("source_component")
            or payload.get("component_id")
            or ""
        ).strip()
        text = str(payload.get("message") or f"{source_action} from {sender or 'unknown'}")

        self._journal.log(
            severity=self._severity_for_payload(payload),
            source_sender=sender,
            source_component=source_component,
            source_action=source_action,
            message=text,
            details=self._details_for_payload(payload),
        )
        return None


class SecurityPolicyMonitor(SecurityJournalMonitor):
    """Security monitor that checks policy, routes allowed traffic, and audits decisions."""

    PROXY_TIMEOUT: float = 10.0
    PROXY_REQUEST_ACTION = "proxy_request"
    PROXY_PUBLISH_ACTION = "proxy_publish"
    LIST_POLICIES_ACTION = "list_policies"

    def __init__(
        self,
        *,
        component_id: str,
        component_type: str,
        topic: str,
        bus: SystemBus,
        journal: JournalRecorder,
        dispatcher: Optional[InfopanelDispatcher] = None,
        policies: Optional[set[PolicyKey]] = None,
    ):
        self._policies = set(policies or set())
        super().__init__(
            component_id=component_id,
            component_type=component_type,
            topic=topic,
            bus=bus,
            journal=journal,
            dispatcher=dispatcher,
        )

    def _register_handlers(self):
        super()._register_handlers()
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

    def _audit(
        self,
        *,
        severity: str,
        source_action: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        self._journal.log(
            severity=severity,
            source_sender=self.topic,
            source_component=self.component_type,
            source_action=source_action,
            message=message,
            details=details or {},
        )

    def _audit_decision(
        self,
        *,
        mode: str,
        decision: str,
        sender_id: str,
        target_topic: str = "",
        target_action: str = "",
        reason: str = "",
        correlation_id: str | None = None,
    ) -> None:
        severity = "info"
        if decision == "denied":
            severity = "critical"
        elif decision in {"invalid", "no_response", "error"}:
            severity = "error"

        details = {
            "mode": mode,
            "decision": decision,
            "sender": sender_id,
            "target_topic": target_topic,
            "target_action": target_action,
        }
        if reason:
            details["reason"] = reason
        if correlation_id:
            details["correlation_id"] = correlation_id

        self._audit(
            severity=severity,
            source_action=f"{self.component_type}.{mode}.{decision}",
            message=f"{mode} {decision} sender={sender_id} target={target_topic}:{target_action}",
            details=details,
        )

    def _message_correlation_id(self, message: Dict[str, Any]) -> str | None:
        correlation_id = message.get("trace_correlation_id") or message.get("correlation_id")
        return str(correlation_id) if correlation_id else None

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
    ) -> bool | Dict[str, Any]:
        pass

    def _handle_proxy_request(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        sender_id = str(message.get("sender") or "").strip()
        target = self._extract_target(payload)
        correlation_id = self._message_correlation_id(message)
        if not sender_id or target is None:
            self._audit_decision(
                mode="request",
                decision="invalid",
                sender_id=sender_id or "unknown",
                reason="invalid_target_or_sender",
                correlation_id=correlation_id,
            )
            return self._deny("invalid_target_or_sender", sender_id or "unknown")

        target_topic, target_action, target_payload = target
        if not self._is_allowed("request", sender_id, target_topic, target_action):
            self._audit_decision(
                mode="request",
                decision="denied",
                sender_id=sender_id,
                target_topic=target_topic,
                target_action=target_action,
                reason="policy_not_found",
                correlation_id=correlation_id,
            )
            return self._deny("policy_not_found", sender_id, target_topic, target_action)

        response = self._route_request(
            target_topic,
            target_action,
            target_payload,
            correlation_id=correlation_id,
        )
        if not isinstance(response, dict):
            self._audit_decision(
                mode="request",
                decision="no_response",
                sender_id=sender_id,
                target_topic=target_topic,
                target_action=target_action,
                correlation_id=correlation_id,
            )
            return {"ok": False, "error": "no_response", "target_topic": target_topic, "target_action": target_action}

        decision = "allowed"
        reason = ""
        if response.get("ok") is False or response.get("error"):
            decision = "error"
            reason = str(response.get("error") or "route_error")
        self._audit_decision(
            mode="request",
            decision=decision,
            sender_id=sender_id,
            target_topic=target_topic,
            target_action=target_action,
            reason=reason,
            correlation_id=correlation_id,
        )
        return {"target_response": response}

    def _handle_proxy_publish(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload") or {}
        sender_id = str(message.get("sender") or "").strip()
        target = self._extract_target(payload)
        correlation_id = self._message_correlation_id(message)
        if not sender_id or target is None:
            self._audit_decision(
                mode="publish",
                decision="invalid",
                sender_id=sender_id or "unknown",
                reason="invalid_target_or_sender",
                correlation_id=correlation_id,
            )
            return self._deny("invalid_target_or_sender", sender_id or "unknown")

        target_topic, target_action, target_payload = target
        if not self._is_allowed("publish", sender_id, target_topic, target_action):
            self._audit_decision(
                mode="publish",
                decision="denied",
                sender_id=sender_id,
                target_topic=target_topic,
                target_action=target_action,
                reason="policy_not_found",
                correlation_id=correlation_id,
            )
            return self._deny("policy_not_found", sender_id, target_topic, target_action)

        route_result = self._route_publish(
            target_topic,
            target_action,
            target_payload,
            correlation_id=correlation_id,
        )
        if isinstance(route_result, dict):
            decision = "allowed"
            reason = ""
            if route_result.get("ok") is False or route_result.get("error"):
                decision = "error"
                reason = str(route_result.get("error") or "route_error")
            self._audit_decision(
                mode="publish",
                decision=decision,
                sender_id=sender_id,
                target_topic=target_topic,
                target_action=target_action,
                reason=reason,
                correlation_id=correlation_id,
            )
            return route_result

        published = bool(route_result)
        self._audit_decision(
            mode="publish",
            decision="allowed" if published else "no_response",
            sender_id=sender_id,
            target_topic=target_topic,
            target_action=target_action,
            correlation_id=correlation_id,
        )
        return {"published": published}

    def _handle_list_policies(self, message: Dict[str, Any]) -> Dict[str, Any]:
        sender_id = str(message.get("sender") or "").strip()
        correlation_id = self._message_correlation_id(message)
        if not sender_id:
            self._audit_decision(
                mode="read",
                decision="invalid",
                sender_id="unknown",
                target_topic=self.topic,
                target_action=self.LIST_POLICIES_ACTION,
                reason="missing_sender",
                correlation_id=correlation_id,
            )
            return self._deny("missing_sender", "unknown", self.topic, self.LIST_POLICIES_ACTION)
        if not self._is_allowed("read", sender_id, self.topic, self.LIST_POLICIES_ACTION):
            self._audit_decision(
                mode="read",
                decision="denied",
                sender_id=sender_id,
                target_topic=self.topic,
                target_action=self.LIST_POLICIES_ACTION,
                reason="policy_not_found",
                correlation_id=correlation_id,
            )
            return self._deny("policy_not_found", sender_id, self.topic, self.LIST_POLICIES_ACTION)

        self._audit_decision(
            mode="read",
            decision="allowed",
            sender_id=sender_id,
            target_topic=self.topic,
            target_action=self.LIST_POLICIES_ACTION,
            correlation_id=correlation_id,
        )
        policies = [
            {"mode": mode, "sender": sender, "topic": topic, "action": action}
            for mode, sender, topic, action in sorted(self._policies)
        ]
        return {"count": len(policies), "policies": policies}
