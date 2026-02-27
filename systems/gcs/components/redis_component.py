"""RedisComponent как отдельная система (BaseSystem) для централизованного состояния НУС."""

from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from typing import Any, Dict, Optional

from broker.system_bus import SystemBus
from shared.base_system import BaseSystem
from shared.topics import SystemTopics

try:
    import redis
except ImportError:
    redis = None  # type: ignore


class RedisComponent(BaseSystem):
    def __init__(self, system_id: str, bus: SystemBus, health_port: Optional[int] = None):
        self.redis_client = None

        self.initial_fleet: Dict[str, Dict[str, Any]] = {
            "drone-001": {"status": "available", "battery": 96},
            "drone-002": {"status": "available", "battery": 91},
            "drone-003": {"status": "available", "battery": 87},
            "drone-004": {"status": "charging", "battery": 44},
        }

        self._init_backend()

        super().__init__(
            system_id=system_id,
            system_type="gcs_redis",
            topic=SystemTopics.GCS_REDIS,
            bus=bus,
            health_port=health_port,
        )

    def _init_backend(self) -> None:
        """Инициализирует backend хранения: только Redis."""
        if redis is None:
            raise RuntimeError("redis package is not installed. Install dependency 'redis>=5.0.0'")

        host = os.getenv("REDIS_HOST", "localhost")
        port = int(os.getenv("REDIS_PORT", "6379"))
        db = int(os.getenv("REDIS_DB", "0"))
        password = os.getenv("REDIS_PASSWORD")

        try:
            client = redis.Redis(
                host=host,
                port=port,
                db=db,
                password=password,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            client.ping()
            self.redis_client = client
            print(f"[gcs_redis] connected to Redis at {host}:{port}/{db}")
        except Exception as exc:
            raise RuntimeError(f"[gcs_redis] Redis unavailable: {exc}") from exc

    def _mission_key(self, mission_id: str) -> str:
        return f"gcs:mission:{mission_id}"

    def _telemetry_key(self, drone_id: str) -> str:
        return f"gcs:telemetry:{drone_id}"

    def _fleet_key(self) -> str:
        return "gcs:fleet"

    def _read_mission(self, mission_id: str) -> Optional[Dict[str, Any]]:
        raw = self.redis_client.get(self._mission_key(mission_id))
        if raw is None:
            return None
        return json.loads(raw)

    def _write_mission(self, mission: Dict[str, Any]) -> None:
        mission_id = mission["mission_id"]
        self.redis_client.set(self._mission_key(mission_id), json.dumps(mission, ensure_ascii=False))
        self.redis_client.sadd("gcs:missions", mission_id)

    def _write_telemetry(self, drone_id: str, telemetry: Dict[str, Any]) -> None:
        self.redis_client.set(self._telemetry_key(drone_id), json.dumps(telemetry, ensure_ascii=False))
        self.redis_client.sadd("gcs:telemetry:index", drone_id)

    def _load_fleet(self) -> Dict[str, Dict[str, Any]]:
        raw = self.redis_client.get(self._fleet_key())
        if raw is None:
            self.redis_client.set(self._fleet_key(), json.dumps(self.initial_fleet, ensure_ascii=False))
            return dict(self.initial_fleet)
        return json.loads(raw)

    def _save_fleet(self, fleet: Dict[str, Dict[str, Any]]) -> None:
        self.redis_client.set(self._fleet_key(), json.dumps(fleet, ensure_ascii=False))

    def _register_handlers(self):
        self.register_handler("redis.save_mission", self._handle_save_mission)
        self.register_handler("redis.get_mission", self._handle_get_mission)
        self.register_handler("redis.update_mission", self._handle_update_mission)
        self.register_handler("redis.upsert_telemetry", self._handle_upsert_telemetry)
        self.register_handler("redis.allocate_drones", self._handle_allocate_drones)
        self.register_handler("redis.release_drones", self._handle_release_drones)
        self.register_handler("redis.get_fleet_status", self._handle_get_fleet_status)

    def _handle_save_mission(self, message: Dict[str, Any]) -> Dict[str, Any]:
        mission = message.get("payload", {}).get("mission", {})
        mission_id = mission.get("mission_id")
        if not mission_id:
            return {"saved": False, "error": "mission_id is required"}
        self._write_mission(mission)
        return {"saved": True, "mission_id": mission_id}

    def _handle_get_mission(self, message: Dict[str, Any]) -> Dict[str, Any]:
        mission_id = message.get("payload", {}).get("mission_id")
        if not mission_id:
            return {"found": False, "error": "mission_id is required"}
        mission = self._read_mission(mission_id)
        if mission is None:
            return {"found": False, "mission_id": mission_id}
        return {"found": True, "mission": mission}

    def _handle_update_mission(self, message: Dict[str, Any]) -> Dict[str, Any]:
        payload = message.get("payload", {})
        mission_id = payload.get("mission_id")
        fields = payload.get("fields", {})
        if not mission_id:
            return {"updated": False, "error": "mission_id is required"}
        mission = self._read_mission(mission_id)
        if mission is None:
            return {"updated": False, "mission_id": mission_id}
        mission.update(fields)
        mission["updated_at"] = datetime.now(timezone.utc).isoformat()
        self._write_mission(mission)
        return {"updated": True, "mission": mission}

    def _handle_upsert_telemetry(self, message: Dict[str, Any]) -> Dict[str, Any]:
        telemetry = message.get("payload", {}).get("telemetry", {})
        drone_id = telemetry.get("drone_id")
        if not drone_id:
            return {"accepted": False, "error": "drone_id is required"}
        self._write_telemetry(drone_id, telemetry)
        return {"accepted": True, "drone_id": drone_id}

    def _handle_allocate_drones(self, message: Dict[str, Any]) -> Dict[str, Any]:
        required_count = int(message.get("payload", {}).get("required_count", 1))
        fleet = self._load_fleet()
        available = [
            drone_id
            for drone_id, state in fleet.items()
            if state.get("status") == "available"
        ]
        selected = available[:required_count]
        for drone_id in selected:
            fleet[drone_id]["status"] = "reserved"
        self._save_fleet(fleet)
        return {
            "allocated_drones": selected,
            "enough": len(selected) >= required_count,
        }

    def _handle_release_drones(self, message: Dict[str, Any]) -> Dict[str, Any]:
        drone_ids = message.get("payload", {}).get("drone_ids", [])
        fleet = self._load_fleet()
        for drone_id in drone_ids:
            if drone_id in fleet:
                fleet[drone_id]["status"] = "available"
        self._save_fleet(fleet)
        return {"released": True, "drone_ids": drone_ids}

    def _handle_get_fleet_status(self, message: Dict[str, Any]) -> Dict[str, Any]:
        fleet = self._load_fleet()
        return {
            "fleet_size": len(fleet),
            "available": sum(1 for x in fleet.values() if x.get("status") == "available"),
            "reserved": sum(1 for x in fleet.values() if x.get("status") == "reserved"),
            "in_mission": sum(1 for x in fleet.values() if x.get("status") == "in_mission"),
            "charging": sum(1 for x in fleet.values() if x.get("status") == "charging"),
        }

    def get_status(self) -> Dict[str, Any]:
        status = super().get_status()
        fleet = self._load_fleet()
        missions_total = self.redis_client.scard("gcs:missions")
        telemetry_items = self.redis_client.scard("gcs:telemetry:index")
        status.update(
            {
                "backend": "redis",
                "missions_total": missions_total,
                "telemetry_items": telemetry_items,
                "fleet_size": len(fleet),
            }
        )
        return status
