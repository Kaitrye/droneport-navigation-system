"""RobotComponent как отдельная система (BaseSystem)."""

from __future__ import annotations

from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from shared.base_system import BaseSystem
from shared.topics import SystemTopics
from systems.gcs.src.contracts import DronePortActions, DroneServiceActions, ExternalTopics


class RobotComponent(BaseSystem):
    def __init__(self, system_id: str, bus: SystemBus, health_port: Optional[int] = None):
        super().__init__(
            system_id=system_id,
            system_type="gcs_robot",
            topic=SystemTopics.GCS_ROBOT,
            bus=bus,
            health_port=health_port,
        )

    def _register_handlers(self):
        self.register_handler("robot.execute_mission", self._handle_execute_mission)
        self.register_handler("robot.abort_mission", self._handle_abort_mission)

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

    def _handle_execute_mission(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload", {})
        mission_id = payload.get("mission_id")
        drone_ids = payload.get("drone_ids", [])
        min_battery = payload.get("min_battery", 70)

        reserve = self.send_to_other_system(
            ExternalTopics.DRONEPORT,
            DronePortActions.RESERVE_SLOTS,
            {"mission_id": mission_id, "drone_ids": drone_ids},
        )
        if not reserve:
            return {"started": False, "error": "droneport.reserve_slots timeout"}

        preflight = self.send_to_other_system(
            ExternalTopics.DRONEPORT,
            DronePortActions.PREFLIGHT_CHECK,
            {"mission_id": mission_id, "drone_ids": drone_ids},
        )
        if not preflight:
            return {"started": False, "error": "droneport.preflight_check timeout"}

        charging = self.send_to_other_system(
            ExternalTopics.DRONEPORT,
            DronePortActions.CHARGE_TO_THRESHOLD,
            {"mission_id": mission_id, "drone_ids": drone_ids, "min_battery": min_battery},
        )
        if not charging:
            return {"started": False, "error": "droneport.charge_to_threshold timeout"}

        release = self.send_to_other_system(
            ExternalTopics.DRONEPORT,
            DronePortActions.RELEASE_FOR_TAKEOFF,
            {"mission_id": mission_id, "drone_ids": drone_ids},
        )
        if not release:
            return {"started": False, "error": "droneport.release_for_takeoff timeout"}

        for drone_id in drone_ids:
            uploaded = self.send_to_other_system(
                ExternalTopics.DRONE_SERVICE,
                DroneServiceActions.UPLOAD_MISSION,
                {"mission_id": mission_id, "drone_id": drone_id},
            )
            if not uploaded:
                return {"started": False, "error": f"upload_mission timeout for {drone_id}"}

            armed = self.send_to_other_system(
                ExternalTopics.DRONE_SERVICE,
                DroneServiceActions.ARM,
                {"mission_id": mission_id, "drone_id": drone_id},
            )
            if not armed:
                return {"started": False, "error": f"arm timeout for {drone_id}"}

            takeoff = self.send_to_other_system(
                ExternalTopics.DRONE_SERVICE,
                DroneServiceActions.TAKEOFF,
                {"mission_id": mission_id, "drone_id": drone_id},
            )
            if not takeoff:
                return {"started": False, "error": f"takeoff timeout for {drone_id}"}

        self.send_to_other_system(
            SystemTopics.GCS_REDIS,
            "redis.update_mission",
            {"mission_id": mission_id, "fields": {"status": "running", "assigned_drones": drone_ids}},
        )

        return {"started": True, "mission_id": mission_id, "drone_ids": drone_ids}

    def _handle_abort_mission(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload", {})
        mission_id = payload.get("mission_id")
        drone_ids = payload.get("drone_ids", [])

        for drone_id in drone_ids:
            self.send_to_other_system(
                ExternalTopics.DRONE_SERVICE,
                DroneServiceActions.ABORT,
                {"mission_id": mission_id, "drone_id": drone_id},
                timeout=2.0,
            )
            self.send_to_other_system(
                ExternalTopics.DRONEPORT,
                DronePortActions.EMERGENCY_RECEIVE,
                {"mission_id": mission_id, "drone_id": drone_id},
                timeout=2.0,
            )

        self.send_to_other_system(
            SystemTopics.GCS_FLEET,
            "fleet.release",
            {"drone_ids": drone_ids},
        )

        return {"aborted": True, "mission_id": mission_id, "drone_ids": drone_ids}
