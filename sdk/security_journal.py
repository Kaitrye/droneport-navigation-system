"""Security journal: structured NDJSON-on-disk recorder with severity levels.

Schema is forward-compatible with Infopanel /log/event API (team 4):
fields ``timestamp_ms``, ``service``, ``service_id``, ``event_type``,
``severity`` and ``message`` mirror that contract. Local-only fields
``source_component``, ``source_sender``, ``source_action`` and ``details``
stay in the NDJSON file for diagnostics and are not sent over the wire.

The optional InfopanelDispatcher pushes records as batches to Infopanel
in a background thread; NDJSON is always written first as the local
durable copy (Infopanel does not support backfill on their side, so the
NDJSON is also our recovery source).
"""

from __future__ import annotations

import json
import logging
import os
import queue
import threading
import time
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any, Dict, List, Optional, Protocol


SEVERITY_LEVELS = (
    "debug",
    "info",
    "notice",
    "warning",
    "error",
    "critical",
    "alert",
    "emergency",
)
SEVERITY_RANK = {level: index for index, level in enumerate(SEVERITY_LEVELS)}

LOG_EVENT_ACTION = "log_event"

MAX_MESSAGE_LEN = 1024


@dataclass
class JournalRecord:
    timestamp_iso: str
    timestamp_ms: int
    service: str
    service_id: int
    severity: str
    message: str
    source_component: str
    source_sender: str
    source_action: str
    details: Dict[str, Any] = field(default_factory=dict)
    event_type: str = "safety_event"

    def to_ndjson_line(self) -> str:
        return json.dumps(asdict(self), default=str, ensure_ascii=False) + "\n"

    def to_infopanel_item(self, *, api_version: str = "1.1.0") -> Dict[str, Any]:
        """Project the record onto the Infopanel POST /log/event contract."""
        return {
            "apiVersion": api_version,
            "timestamp": int(self.timestamp_ms),
            "event_type": self.event_type,
            "service": self.service,
            "service_id": int(self.service_id),
            "severity": self.severity,
            "message": str(self.message)[:MAX_MESSAGE_LEN],
        }


class _RecordSink(Protocol):
    def enqueue(self, record: "JournalRecord") -> None: ...


class JournalRecorder:
    """Append-only NDJSON writer with severity filter. Thread-safe."""

    def __init__(
        self,
        file_path: str,
        *,
        min_severity: str = "info",
        service: str = "",
        service_id: int = 1,
        logger: Optional[logging.Logger] = None,
        sink: Optional[_RecordSink] = None,
    ) -> None:
        self._file_path = file_path
        self._service = service
        self._service_id = int(service_id)
        self._logger = logger or logging.getLogger(__name__)
        self._lock = threading.Lock()
        self._min_rank = SEVERITY_RANK.get(min_severity.lower(), SEVERITY_RANK["info"])
        self._sink = sink

        if file_path:
            directory = os.path.dirname(file_path)
            if directory:
                try:
                    os.makedirs(directory, exist_ok=True)
                except OSError as exc:
                    self._logger.error("journal: cannot create dir %s: %s", directory, exc)

    def build_record(
        self,
        *,
        severity: str,
        source_sender: str,
        source_component: str,
        source_action: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> Optional[JournalRecord]:
        sev = (severity or "").lower().strip()
        rank = SEVERITY_RANK.get(sev)
        if rank is None:
            self._logger.warning("journal: invalid severity %r, dropping event %r", severity, source_action)
            return None
        if rank < self._min_rank:
            return None

        now = datetime.now(timezone.utc)
        return JournalRecord(
            timestamp_iso=now.isoformat(timespec="milliseconds"),
            timestamp_ms=int(now.timestamp() * 1000),
            service=self._service,
            service_id=self._service_id,
            severity=sev,
            message=(message or "")[:MAX_MESSAGE_LEN],
            source_component=source_component or "",
            source_sender=source_sender or "",
            source_action=source_action or "",
            details=details or {},
        )

    def write(self, record: JournalRecord) -> None:
        if self._file_path:
            line = record.to_ndjson_line()
            with self._lock:
                try:
                    with open(self._file_path, "a", encoding="utf-8") as fh:
                        fh.write(line)
                except OSError as exc:
                    self._logger.error(
                        "journal: write failed (%s): %s | record=%s",
                        self._file_path,
                        exc,
                        line.rstrip("\n"),
                    )
        if self._sink is not None:
            try:
                self._sink.enqueue(record)
            except Exception as exc:  # pragma: no cover - defensive
                self._logger.error("journal: sink enqueue failed: %s", exc)

    def log(
        self,
        *,
        severity: str,
        source_sender: str,
        source_component: str,
        source_action: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> None:
        record = self.build_record(
            severity=severity,
            source_sender=source_sender,
            source_component=source_component,
            source_action=source_action,
            message=message,
            details=details,
        )
        if record is not None:
            self.write(record)


class InfopanelDispatcher:
    """Background batched HTTPS sender for Infopanel /log/event.

    Records are projected to the Infopanel contract and sent as JSON arrays
    of size up to ``batch_size``. Sending happens off the request-handling
    thread; if the queue fills (Infopanel down for a long time) the OLDEST
    record is dropped — security violations should still get through and the
    full history remains in the local NDJSON.

    Failures: 5xx and network errors retry with exponential backoff up to
    ``max_retries`` per batch. 4xx is logged and not retried (broken
    payload or bad API key — re-trying won't help).

    HTTP client: ``requests`` (already in project dependencies).
    """

    DEFAULT_API_VERSION = "1.1.0"

    def __init__(
        self,
        url: str,
        api_key: str,
        *,
        batch_size: int = 50,
        flush_interval_s: float = 5.0,
        max_retries: int = 5,
        retry_backoff_s: float = 2.0,
        queue_max: int = 10000,
        http_timeout_s: float = 10.0,
        verify_tls: bool = True,
        api_version: str = DEFAULT_API_VERSION,
        session: Any = None,
        logger: Optional[logging.Logger] = None,
    ) -> None:
        self._url = url
        self._api_key = api_key
        self._batch_size = max(1, int(batch_size))
        self._flush_interval_s = float(flush_interval_s)
        self._max_retries = max(0, int(max_retries))
        self._retry_backoff_s = float(retry_backoff_s)
        self._http_timeout_s = float(http_timeout_s)
        self._verify_tls = bool(verify_tls)
        self._api_version = api_version
        self._logger = logger or logging.getLogger(__name__)

        self._queue: "queue.Queue[JournalRecord]" = queue.Queue(maxsize=max(1, int(queue_max)))
        self._stop_event = threading.Event()
        self._thread: Optional[threading.Thread] = None
        self._session = session  # injectable for tests; lazy-created if None
        self._enabled = bool(url and api_key)
        if not self._enabled:
            self._logger.warning(
                "infopanel: dispatcher disabled (URL or API key missing) — local NDJSON only"
            )

    # ---- Lifecycle ----

    def start(self) -> None:
        if not self._enabled or self._thread is not None:
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._run, name="infopanel-dispatcher", daemon=True
        )
        self._thread.start()

    def stop(self, *, drain_timeout_s: float = 5.0) -> None:
        if self._thread is None:
            return
        self._stop_event.set()
        self._thread.join(timeout=drain_timeout_s)
        self._thread = None

    # ---- Sink protocol ----

    def enqueue(self, record: JournalRecord) -> None:
        if not self._enabled:
            return
        try:
            self._queue.put_nowait(record)
        except queue.Full:
            try:
                self._queue.get_nowait()  # drop oldest
            except queue.Empty:
                pass
            try:
                self._queue.put_nowait(record)
            except queue.Full:
                self._logger.warning("infopanel: queue full, dropped record %s", record.source_action)

    # ---- Internals ----

    def _ensure_session(self) -> Any:
        if self._session is not None:
            return self._session
        import requests  # local import keeps tests light

        self._session = requests.Session()
        self._session.headers.update({
            "X-API-Key": self._api_key,
            "Content-Type": "application/json",
        })
        return self._session

    def _drain_batch(self) -> List[JournalRecord]:
        deadline = time.monotonic() + self._flush_interval_s
        batch: List[JournalRecord] = []
        try:
            first = self._queue.get(timeout=self._flush_interval_s)
        except queue.Empty:
            return batch
        batch.append(first)

        while len(batch) < self._batch_size and time.monotonic() < deadline:
            try:
                batch.append(self._queue.get_nowait())
            except queue.Empty:
                break
        return batch

    def _run(self) -> None:
        while not self._stop_event.is_set():
            batch = self._drain_batch()
            if not batch:
                continue
            payload = [r.to_infopanel_item(api_version=self._api_version) for r in batch]
            self._send_with_retry(payload)

    def _send_with_retry(self, payload: List[Dict[str, Any]]) -> None:
        session = self._ensure_session()
        for attempt in range(self._max_retries + 1):
            if self._stop_event.is_set():
                return
            try:
                resp = session.post(
                    self._url,
                    json=payload,
                    timeout=self._http_timeout_s,
                    verify=self._verify_tls,
                )
                status = resp.status_code
                if 200 <= status < 300:
                    return
                if 400 <= status < 500:
                    self._logger.error(
                        "infopanel: 4xx %s on batch of %d (no retry): %s",
                        status, len(payload), resp.text[:300] if hasattr(resp, "text") else "",
                    )
                    return
                # 5xx — retry
                self._logger.warning(
                    "infopanel: %s on batch of %d (attempt %d/%d)",
                    status, len(payload), attempt + 1, self._max_retries + 1,
                )
            except Exception as exc:
                self._logger.warning(
                    "infopanel: network error on batch of %d (attempt %d/%d): %s",
                    len(payload), attempt + 1, self._max_retries + 1, exc,
                )

            if attempt < self._max_retries:
                delay = self._retry_backoff_s * (2 ** attempt)
                if self._stop_event.wait(timeout=delay):
                    return

        self._logger.error(
            "infopanel: dropping batch of %d after %d retries (records remain in NDJSON)",
            len(payload), self._max_retries,
        )


__all__ = [
    "SEVERITY_LEVELS",
    "SEVERITY_RANK",
    "LOG_EVENT_ACTION",
    "MAX_MESSAGE_LEN",
    "JournalRecord",
    "JournalRecorder",
    "InfopanelDispatcher",
]
