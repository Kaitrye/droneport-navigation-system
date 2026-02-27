"""Unit тесты компонентной архитектуры GCS."""

from unittest.mock import MagicMock, patch


class TestMissionComponent:
    def _build_component(self):
        from systems.gcs.components.mission_component import MissionComponent

        bus = MagicMock()
        bus.start = MagicMock()
        bus.subscribe = MagicMock()

        def request_stub(topic, message, timeout=10.0):
            action = message.get("action")
            if action == "redis.save_mission":
                mission_id = message.get("payload", {}).get("mission", {}).get("mission_id")
                return {"success": True, "payload": {"saved": True, "mission_id": mission_id}}
            if action == "orchestrator.plan":
                return {
                    "success": True,
                    "payload": {
                        "accepted": True,
                        "status": "running",
                        "drone_ids": ["drone-001"],
                    },
                }
            if action == "orchestrator.cancel":
                return {"success": True, "payload": {"cancelled": True, "mission_id": "m-test"}}
            if action == "redis.get_mission":
                return {
                    "success": True,
                    "payload": {"found": True, "mission": {"mission_id": "m-test"}},
                }
            return {"success": False, "payload": {}}

        bus.request = MagicMock(side_effect=request_stub)

        with patch("shared.base_system.threading"):
            component = MissionComponent(system_id="gcs_mission_test", bus=bus, health_port=None)
        return component, bus

    def test_task_submit(self):
        from systems.gcs.src.contracts import GCSActions

        component, bus = self._build_component()
        result = component._handle_task_submit(
            {
                "action": GCSActions.TASK_SUBMIT,
                "sender": "api",
                "payload": {"task_id": "task-1", "requirements": {"count": 1}},
            }
        )

        assert result["accepted"] is True
        assert result["status"] == "running"
        assert bus.request.called

    def test_mission_cancel(self):
        from systems.gcs.src.contracts import GCSActions

        component, _ = self._build_component()
        result = component._handle_mission_cancel(
            {
                "action": GCSActions.MISSION_CANCEL,
                "sender": "api",
                "payload": {"mission_id": "m-test"},
            }
        )
        assert result["cancelled"] is True


class TestRedisComponent:
    def _build_component(self):
        from systems.gcs.components.redis_component import RedisComponent

        bus = MagicMock()
        bus.start = MagicMock()
        bus.subscribe = MagicMock()

        with patch("shared.base_system.threading"):
            component = RedisComponent(system_id="gcs_redis_test", bus=bus, health_port=None)
        return component

    def test_allocate_and_release_drones(self):
        component = self._build_component()

        allocate = component._handle_allocate_drones(
            {"payload": {"required_count": 2}}
        )
        assert allocate["enough"] is True
        assert len(allocate["allocated_drones"]) == 2

        release = component._handle_release_drones(
            {"payload": {"drone_ids": allocate["allocated_drones"]}}
        )
        assert release["released"] is True


class TestTelemetryComponent:
    def _build_component(self):
        from systems.gcs.components.telemetry_component import TelemetryComponent

        bus = MagicMock()
        bus.start = MagicMock()
        bus.subscribe = MagicMock()
        bus.request = MagicMock(
            return_value={
                "success": True,
                "payload": {"accepted": True, "drone_id": "drone-001"},
            }
        )

        with patch("shared.base_system.threading"):
            component = TelemetryComponent(system_id="gcs_telemetry_test", bus=bus, health_port=None)
        return component, bus

    def test_telemetry_update(self):
        from systems.gcs.src.contracts import GCSActions

        component, bus = self._build_component()
        result = component._handle_telemetry_update(
            {
                "action": GCSActions.TELEMETRY_UPDATE,
                "sender": "robot",
                "payload": {"drone_id": "drone-001", "battery": 80},
            }
        )

        assert result["accepted"] is True
        assert result["drone_id"] == "drone-001"
        assert bus.request.called
