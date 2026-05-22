"""Topics and actions for the GCS security monitor."""

import os


_NS = os.environ.get("SYSTEM_NAMESPACE", "")
_P = f"{_NS}." if _NS else ""


class ComponentTopics:
    SECURITY_MONITOR = f"{_P}components.gcs_security_monitor"


class SecurityMonitorActions:
    LOG_EVENT = "log_event"
    SECURITY_AUDIT = "security_audit"
