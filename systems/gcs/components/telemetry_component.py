"""TelemetryComponent как отдельная система (BaseSystem)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from shared.base_system import BaseSystem
from shared.topics import SystemTopics
from systems.gcs.src.contracts import GCSActions


class TelemetryComponent(BaseSystem):
    def __init__(self, system_id: str, bus: SystemBus, health_port: Optional[int] = None):
        super().__init__(
            system_id=system_id,
            system_type="gcs_telemetry",
            topic=SystemTopics.GCS_TELEMETRY,
            bus=bus,
            health_port=health_port,
        )

    def _register_handlers(self):
        self.register_handler(GCSActions.TELEMETRY_UPDATE, self._handle_telemetry_update)

    def send_to_other_system(self, target_topic: str, action: str, payload: dict, timeout: float = 10.0) -> Optional[dict]:
        return self.bus.request(
            target_topic,
            {
                "action": action,
                "sender": self.system_id,
                "payload": payload,
            },
            timeout=timeout,
        )

    def _handle_telemetry_update(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload", {})
        drone_id = payload.get("drone_id")
        if not drone_id:
            return {"accepted": False, "error": "drone_id is required"}

        response = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.upsert_telemetry",
            {"telemetry": payload},
        )
        if not response or not response.get("success"):
            return {"accepted": False, "error": "redis unavailable"}
        return response.get("payload", {"accepted": True, "drone_id": drone_id})
