"""FleetComponent как отдельная система (BaseSystem)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from shared.base_system import BaseSystem
from shared.topics import SystemTopics


class FleetComponent(BaseSystem):
    def __init__(self, system_id: str, bus: SystemBus, health_port: Optional[int] = None):
        super().__init__(
            system_id=system_id,
            system_type="gcs_fleet",
            topic=SystemTopics.GCS_FLEET,
            bus=bus,
            health_port=health_port,
        )

    def _register_handlers(self):
        self.register_handler("fleet.allocate", self._handle_allocate)
        self.register_handler("fleet.release", self._handle_release)
        self.register_handler("fleet.get_status", self._handle_get_status)

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

    def _handle_allocate(self, message: Dict[str, Any]) -> Dict[str, Any]:
        required_count = int(message.get("payload", {}).get("required_count", 1))
        response = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.allocate_drones",
            {"required_count": required_count},
        )
        if not response or not response.get("success"):
            return {"allocated_drones": [], "enough": False, "error": "redis unavailable"}
        return response.get("payload", {"allocated_drones": [], "enough": False})

    def _handle_release(self, message: Dict[str, Any]) -> Dict[str, Any]:
        drone_ids = message.get("payload", {}).get("drone_ids", [])
        response = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.release_drones",
            {"drone_ids": drone_ids},
        )
        if not response or not response.get("success"):
            return {"released": False, "drone_ids": drone_ids}
        return response.get("payload", {"released": False, "drone_ids": drone_ids})

    def _handle_get_status(self, message: Dict[str, Any]) -> Dict[str, Any]:
        response = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.get_fleet_status",
            {},
        )
        if not response or not response.get("success"):
            return {"error": "redis unavailable"}
        return response.get("payload", {})
