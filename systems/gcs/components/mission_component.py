"""MissionComponent как отдельная система (BaseSystem)."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Dict, Optional
from uuid import uuid4

from broker.system_bus import SystemBus
from shared.base_system import BaseSystem
from shared.topics import SystemTopics
from systems.gcs.src.contracts import GCSActions, MissionStatus


class MissionComponent(BaseSystem):
    def __init__(self, system_id: str, bus: SystemBus, health_port: Optional[int] = None):
        super().__init__(
            system_id=system_id,
            system_type="gcs_mission",
            topic=SystemTopics.GCS_MISSION,
            bus=bus,
            health_port=health_port,
        )

    def _register_handlers(self):
        self.register_handler(GCSActions.TASK_SUBMIT, self._handle_task_submit)
        self.register_handler(GCSActions.MISSION_CANCEL, self._handle_mission_cancel)
        self.register_handler(GCSActions.GET_MISSION, self._handle_get_mission)

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

    def _handle_task_submit(self, message: Dict[str, Any]) -> Dict[str, Any]:
        task_payload = message.get("payload", {})
        mission_id = task_payload.get("mission_id") or f"m-{uuid4().hex[:12]}"
        now = datetime.now(timezone.utc).isoformat()
        mission = {
            "mission_id": mission_id,
            "task_id": task_payload.get("task_id", f"t-{uuid4().hex[:8]}"),
            "task": task_payload,
            "status": MissionStatus().CREATED,
            "assigned_drones": [],
            "created_at": now,
            "updated_at": now,
        }

        saved = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.save_mission",
            {"mission": mission},
        )
        if not saved or not saved.get("success"):
            return {"accepted": False, "mission_id": mission_id, "error": "failed to save mission"}

        orchestrated = self.send_to_other_system(
            SystemTopics.GCS_ORCHESTRATOR,
            "orchestrator.plan",
            {"mission_id": mission_id, "task": task_payload},
        )

        if not orchestrated or not orchestrated.get("success"):
            return {"accepted": False, "mission_id": mission_id, "error": "orchestrator unavailable"}

        result_payload = orchestrated.get("payload", {})
        return {
            "accepted": bool(result_payload.get("accepted", False)),
            "mission_id": mission_id,
            "status": result_payload.get("status", MissionStatus().FAILED),
            "drone_ids": result_payload.get("drone_ids", []),
        }

    def _handle_mission_cancel(self, message: Dict[str, Any]) -> Dict[str, Any]:
        mission_id = message.get("payload", {}).get("mission_id")
        if not mission_id:
            return {"cancelled": False, "error": "mission_id is required"}

        response = self.send_to_other_system(
            SystemTopics.GCS_ORCHESTRATOR,
            "orchestrator.cancel",
            {"mission_id": mission_id},
        )
        if not response or not response.get("success"):
            return {"cancelled": False, "mission_id": mission_id, "error": "orchestrator unavailable"}

        return response.get("payload", {"cancelled": False, "mission_id": mission_id})

    def _handle_get_mission(self, message: Dict[str, Any]) -> Dict[str, Any]:
        mission_id = message.get("payload", {}).get("mission_id")
        if not mission_id:
            return {"error": "mission_id is required"}

        response = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.get_mission",
            {"mission_id": mission_id},
        )
        if not response or not response.get("success"):
            return {"error": "redis unavailable"}
        return response.get("payload", {})
