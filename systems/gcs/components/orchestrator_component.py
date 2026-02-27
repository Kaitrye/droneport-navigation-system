"""OrchestratorComponent как отдельная система (BaseSystem)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from shared.base_system import BaseSystem
from shared.topics import SystemTopics
from systems.gcs.src.contracts import MissionStatus


class OrchestratorComponent(BaseSystem):
    def __init__(self, system_id: str, bus: SystemBus, health_port: Optional[int] = None):
        super().__init__(
            system_id=system_id,
            system_type="gcs_orchestrator",
            topic=SystemTopics.GCS_ORCHESTRATOR,
            bus=bus,
            health_port=health_port,
        )

    def _register_handlers(self):
        self.register_handler("orchestrator.plan", self._handle_plan)
        self.register_handler("orchestrator.cancel", self._handle_cancel)

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

    def _handle_plan(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload", {})
        mission_id = payload.get("mission_id")
        task = payload.get("task", {})
        requirements = task.get("requirements", {})
        required_count = int(requirements.get("count", task.get("min_drones", 1)))
        min_battery = int(requirements.get("min_battery", 70))

        fleet_response = self.send_to_other_system(
            SystemTopics.GCS_FLEET,
            "fleet.allocate",
            {"required_count": max(1, required_count)},
        )
        if not fleet_response or not fleet_response.get("success"):
            return {"accepted": False, "status": MissionStatus().FAILED, "error": "fleet unavailable"}

        allocated_payload = fleet_response.get("payload", {})
        drone_ids = allocated_payload.get("allocated_drones", [])
        if not allocated_payload.get("enough", False):
            self.send_to_other_system(
                SystemTopics.GCS_REDIS,
                "redis.update_mission",
                {"mission_id": mission_id, "fields": {"status": MissionStatus().FAILED}},
            )
            return {"accepted": False, "status": MissionStatus().FAILED, "error": "not enough drones"}

        self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.update_mission",
            {
                "mission_id": mission_id,
                "fields": {
                    "status": MissionStatus().PLANNED,
                    "assigned_drones": drone_ids,
                },
            },
        )

        robot_response = self.send_to_other_system(
            SystemTopics.GCS_ROBOT,
            "robot.execute_mission",
            {
                "mission_id": mission_id,
                "drone_ids": drone_ids,
                "min_battery": min_battery,
            },
        )

        if not robot_response or not robot_response.get("success"):
            self.send_to_other_system(
                SystemTopics.GCS_REDIS,
                "redis.update_mission",
                {"mission_id": mission_id, "fields": {"status": MissionStatus().FAILED}},
            )
            return {"accepted": False, "status": MissionStatus().FAILED, "error": "robot unavailable"}

        robot_payload = robot_response.get("payload", {})
        if not robot_payload.get("started", False):
            self.send_to_other_system(
                SystemTopics.GCS_REDIS,
                "redis.update_mission",
                {"mission_id": mission_id, "fields": {"status": MissionStatus().FAILED}},
            )
            return {
                "accepted": False,
                "status": MissionStatus().FAILED,
                "drone_ids": drone_ids,
                "error": robot_payload.get("error", "robot start failed"),
            }

        self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.update_mission",
            {"mission_id": mission_id, "fields": {"status": MissionStatus().RUNNING}},
        )

        return {
            "accepted": True,
            "status": MissionStatus().RUNNING,
            "drone_ids": drone_ids,
        }

    def _handle_cancel(self, message: Dict[str, Any]) -> Dict[str, Any]:
        mission_id = message.get("payload", {}).get("mission_id")
        if not mission_id:
            return {"cancelled": False, "error": "mission_id is required"}

        mission_response = self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.get_mission",
            {"mission_id": mission_id},
        )
        drone_ids = []
        if mission_response and mission_response.get("success"):
            mission_payload = mission_response.get("payload", {})
            mission = mission_payload.get("mission", {})
            drone_ids = mission.get("assigned_drones", [])

        self.send_to_other_system(
            SystemTopics.GCS_ROBOT,
            "robot.abort_mission",
            {"mission_id": mission_id, "drone_ids": drone_ids},
        )

        self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.update_mission",
            {"mission_id": mission_id, "fields": {"status": MissionStatus().CANCELLED}},
        )

        return {"cancelled": True, "mission_id": mission_id}
