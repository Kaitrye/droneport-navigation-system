"""Контракты и константы сообщений для GCS."""

from dataclasses import dataclass


class GCSActions:
    TASK_SUBMIT = "task.submit"
    MISSION_CANCEL = "mission.cancel"
    TELEMETRY_UPDATE = "telemetry.update"
    GET_MISSION = "mission.get"
    GET_FLEET_STATUS = "fleet.get_status"


class GCSEvents:
    MISSION_CREATED = "mission.created"
    MISSION_STARTED = "mission.started"
    MISSION_FAILED = "mission.failed"
    MISSION_CANCELLED = "mission.cancelled"
    MISSION_ABORTED = "mission.aborted"
    GROUP_FORMED = "orchestrator.group.formed"
    ROBOT_STATE_CHANGED = "robot.state.changed"
    ROBOT_ERROR = "robot.error"


class ExternalTopics:
    DRONE_SERVICE = "external.drone_service"
    DRONEPORT = "systems.droneport"


class DroneServiceActions:
    UPLOAD_MISSION = "upload_mission"
    ARM = "arm"
    TAKEOFF = "takeoff"
    ABORT = "abort"


class DronePortActions:
    RESERVE_SLOTS = "reserve_slots"
    PREFLIGHT_CHECK = "preflight_check"
    CHARGE_TO_THRESHOLD = "charge_to_threshold"
    RELEASE_FOR_TAKEOFF = "release_for_takeoff"
    EMERGENCY_RECEIVE = "emergency_receive"


@dataclass(frozen=True)
class MissionStatus:
    CREATED: str = "created"
    PLANNED: str = "planned"
    RUNNING: str = "running"
    FAILED: str = "failed"
    CANCELLED: str = "cancelled"
    ABORTED: str = "aborted"
