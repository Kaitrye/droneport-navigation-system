"""Configuration for the GCS security monitor."""

import os
from typing import Optional

from .topics import ComponentTopics


def component_topic() -> str:
    return (
        os.environ.get("COMPONENT_TOPIC")
        or os.environ.get("GCS_SECURITY_MONITOR_TOPIC")
        or ComponentTopics.SECURITY_MONITOR
    ).strip()


def journal_file_path() -> str:
    return (
        os.environ.get("SECURITY_JOURNAL_FILE_PATH")
        or "/var/log/drones/gcs_security_journal.ndjson"
    ).strip()


def journal_min_severity() -> str:
    return (os.environ.get("SECURITY_JOURNAL_MIN_SEVERITY") or "info").strip().lower()


def service_name() -> str:
    return (os.environ.get("SECURITY_JOURNAL_SERVICE_NAME") or "GCS").strip()


def service_id() -> int:
    raw = (os.environ.get("SECURITY_JOURNAL_SERVICE_ID") or "1").strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return value if 1 <= value <= 1000 else 1


def _get_float(name: str, default: float, *, min_value: Optional[float] = None) -> float:
    raw = os.environ.get(name)
    value = float(default) if raw is None or str(raw).strip() == "" else float(raw)
    if min_value is not None and value < min_value:
        raise ValueError(f"{name} must be >= {min_value}, got {value}")
    return value


def infopanel_url() -> str:
    return (os.environ.get("INFOPANEL_URL") or "").strip()


def infopanel_api_key() -> str:
    return (os.environ.get("INFOPANEL_API_KEY") or "").strip()


def infopanel_batch_size() -> int:
    raw = (os.environ.get("INFOPANEL_BATCH_SIZE") or "").strip()
    if not raw:
        return 50
    try:
        return max(1, min(int(raw), 100))
    except ValueError:
        return 50


def infopanel_flush_interval_s() -> float:
    return _get_float("INFOPANEL_FLUSH_INTERVAL_S", 5.0, min_value=0.1)


def infopanel_max_retries() -> int:
    raw = (os.environ.get("INFOPANEL_MAX_RETRIES") or "").strip()
    if not raw:
        return 5
    try:
        return max(0, int(raw))
    except ValueError:
        return 5


def infopanel_verify_tls() -> bool:
    return (os.environ.get("INFOPANEL_VERIFY_TLS") or "true").strip().lower() != "false"
