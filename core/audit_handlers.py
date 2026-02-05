import importlib

# Audit handlers: Loki-based fail-safe handler and persistent backend
import json
import logging
import os
import queue
import sys
import threading
import time


class DaemonThreadPool:
    """A simple daemon thread pool with a bounded queue.

    - Workers are daemon threads, so they don't prevent process shutdown.
    - `submit(fn, *args, **kwargs)` attempts a non-blocking enqueue. If the
      queue is full and `drop_on_full` is True, the task is dropped and a
      DEBUG message is logged. This keeps emission best-effort and non-blocking.
    """

    def __init__(
        self, size: int = 4, max_queue: int = 4096, drop_on_full: bool = True, name_prefix: str = "loki-worker"
    ):
        self._q: queue.Queue = queue.Queue(maxsize=max_queue)
        self._size = max(1, int(size))
        self._drop_on_full = bool(drop_on_full)
        self._workers: list[threading.Thread] = []
        self._started = False
        self._name_prefix = name_prefix

    def _start(self):
        if self._started:
            return
        self._started = True
        for i in range(self._size):
            t = threading.Thread(target=self._run, name=f"{self._name_prefix}-{i}", daemon=True)
            t.start()
            self._workers.append(t)

    def _run(self):
        while True:
            fn, args, kwargs = self._q.get()
            try:
                fn(*args, **kwargs)
            except Exception as exc:  # pragma: no cover - best-effort
                logging.getLogger(__name__).debug("DaemonThreadPool worker exception: %s", exc)
            finally:
                try:
                    self._q.task_done()
                except Exception:
                    pass

    def submit(self, fn, *args, block_on_full: bool = False):
        """Submit a callable to be executed by a pool worker.

        - If the queue is full: if `block_on_full` is True we will block until space
          is available; otherwise we drop the task and log a DEBUG message.
        """
        self._start()
        try:
            if block_on_full:
                self._q.put((fn, args, {}))
            else:
                self._q.put_nowait((fn, args, {}))
        except queue.Full:
            if self._drop_on_full:
                logging.getLogger(__name__).debug("DaemonThreadPool queue full: dropping task")
            else:
                # If not drop_on_full, block until it fits
                try:
                    self._q.put((fn, args, {}))
                except Exception:
                    logging.getLogger(__name__).debug("DaemonThreadPool failed to enqueue task after retry")

    def flush(self, timeout: float | None = None) -> bool:
        """Wait for the queue to be drained and workers to finish processing.

        Returns True if the queue was drained before the optional timeout, False otherwise.
        """
        # Ensure workers are running
        self._start()
        if timeout is None:
            # Block until all queued tasks are done
            try:
                self._q.join()
                return True
            except Exception:
                return False
        # Wait with timeout
        end = time.time() + float(timeout)
        while time.time() < end:
            if self._q.empty():
                # Wait a short moment to allow worker to call task_done
                time.sleep(0.01)
                if self._q.empty():
                    return True
            time.sleep(0.01)
        return False


from datetime import datetime, timezone

from django.conf import settings

# Do NOT import Django models at module import time (prevents AppRegistryNotReady during logging configuration)
# Models are imported lazily inside backend methods to avoid importing them before Django apps are ready.


def _audit_enabled() -> bool:
    """Return True when audit is enabled.

    Behaviour:
    - Use `settings.AUDIT_ENABLED` (controlled via env var `AUDIT_ENABLED`) as the single source of truth.
    """
    return bool(getattr(settings, "AUDIT_ENABLED", True))


class FailSafeLokiHandler(logging.Handler):
    """Fallback logging handler that writes audit events to a local file.

    We intentionally avoid external network calls (no dependency on `logging_loki` or
    `requests`). Events are written as either raw formatted messages or JSON lines when
    dynamic labels are present. This keeps audit emission resilient and easily
    scrappable by Grafana Alloy.
    """

    def __init__(
        self, url: str | None = None, tags: dict | None = None, fallback_filename: str | None = None, level=logging.INFO
    ):
        super().__init__(level)
        # Keep attributes for compatibility with previous interface
        self.url = url
        self.tags = tags or {"application": getattr(settings, "LOKI_APPLICATION", "business_suite")}

        # Determine fallback filename safely
        if fallback_filename:
            self.fallback_filename = fallback_filename
        else:
            base_dir = getattr(settings, "BASE_DIR", None)
            self.fallback_filename = (
                os.path.join(str(base_dir), "logs", "audit_degraded.log") if base_dir else "audit_degraded.log"
            )

        # Ensure directory exists and initialize file handler
        try:
            log_dir = os.path.dirname(self.fallback_filename)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            self._file_handler = logging.FileHandler(self.fallback_filename)
        except Exception:
            self._file_handler = logging.NullHandler()

        self._file_handler.setLevel(level)
        self._console = logging.StreamHandler()

    def emit(self, record: logging.LogRecord) -> None:
        """Write the record to the fallback file. If `extra` contains dynamic labels
        (e.g., `source` / `audit`), write a JSON line containing the message, timestamp,
        and labels so it's easy to query in Grafana/Loki after Alloy ingestion.
        """
        try:
            message = self.format(record)

            # Extract dynamic labels from the LogRecord
            dynamic_labels: dict = {}
            try:
                for key in ("source", "audit"):
                    if key in record.__dict__ and record.__dict__[key] is not None:
                        val = record.__dict__[key]
                        dynamic_labels[key] = val
            except Exception:
                dynamic_labels = {}

            if dynamic_labels:
                payload = {
                    "ts": datetime.now(timezone.utc).isoformat(),
                    "level": logging.getLevelName(record.levelno),
                    "logger": record.name,
                    "message": message,
                    "labels": {
                        k: (str(v).lower() if isinstance(v, bool) else str(v)) for k, v in dynamic_labels.items()
                    },
                }
                line = json.dumps(payload)
            else:
                # Plain message line
                line = f"{datetime.now(timezone.utc).isoformat()} {logging.getLevelName(record.levelno)} {record.name} {message}"

            # Append line to fallback file
            try:
                # Use the underlying file handler to preserve permissions/rotation behaviour
                self._file_handler.emit(
                    logging.LogRecord(record.name, record.levelno, record.pathname, record.lineno, line, (), None)
                )
            except Exception:
                # Final fallback: emit to console
                self._console.emit(record)
        except Exception:
            try:
                self._console.emit(record)
            except Exception:
                pass


class PersistentLokiBackend:
    """A persistent audit backend that stores audit events to the DB and emits a structured log via the `audit` logger.

    Behaviour mirrors the previous audit backend but sends logs to Loki via `audit` logger which will be
    handled by `FailSafeLokiHandler` when configured.
    """

    def __init__(self, logger_name: str = "audit"):
        self.logger = logging.getLogger(logger_name)

        # Initialize a daemon thread pool for async emission.
        pool_size = int(getattr(settings, "LOKI_EMITTER_POOL_SIZE", 4))
        max_queue = int(getattr(settings, "LOKI_EMITTER_QUEUE_MAXSIZE", 4096))
        drop_on_full = bool(getattr(settings, "LOKI_EMITTER_DROP_ON_FULL", True))
        self._pool = DaemonThreadPool(size=pool_size, max_queue=max_queue, drop_on_full=drop_on_full)

    def _emit_async(self, level: str, message: str, extra: dict | None = None):
        """Emit a structured audit event asynchronously.

        Behaviour:
        - Asynchronously append the event as a JSON line to `logs/audit.log` (or
          configurable via `AUDIT_LOG_FILE` setting).
        - Also emit via the configured `audit` logger for compatibility with
          existing logging handlers.
        """

        audit_file = getattr(settings, "AUDIT_LOG_FILE", None)
        if not audit_file:
            base_dir = getattr(settings, "BASE_DIR", None)
            audit_file = os.path.join(str(base_dir) if base_dir else ".", "logs", "audit.log")

        def _worker():
            try:
                # First: append to the audit file as a JSON line
                try:
                    record_payload = {
                        "ts": datetime.now(timezone.utc).isoformat(),
                        "level": level.upper(),
                        "message": message,
                        "extra": extra or {},
                    }
                    # Ensure directory exists
                    try:
                        os.makedirs(os.path.dirname(audit_file), exist_ok=True)
                    except Exception:
                        pass
                    with open(audit_file, "a", encoding="utf-8") as fh:
                        fh.write(json.dumps(record_payload) + "\n")
                except Exception as exc:  # pragma: no cover - best-effort
                    logging.getLogger(__name__).debug("Failed to write audit file: %s", exc)

                # Second: emit via logger for compatibility
                try:
                    level_fn = getattr(self.logger, level.lower(), self.logger.info)
                    if extra is None:
                        level_fn(message)
                    else:
                        level_fn(message, extra=extra)
                except Exception as exc:  # pragma: no cover - best-effort
                    logging.getLogger(__name__).debug("Failed to emit via audit logger: %s", exc)
            except Exception as exc:  # pragma: no cover - best-effort
                logging.getLogger(__name__).debug("Error in audit worker: %s", exc)

        # Submit to the pool (non-blocking; pool will drop when full if configured)
        try:
            self._pool.submit(_worker, block_on_full=False)
        except Exception as exc:  # pragma: no cover - best-effort
            logging.getLogger(__name__).debug("DaemonThreadPool.submit failed: %s", exc)

    def flush_emitter(self, timeout: float | None = None) -> bool:
        """Flush the emitter pool - wait for queued tasks to be processed.

        Returns True if the queue was drained before the optional timeout, False otherwise.
        """
        try:
            return self._pool.flush(timeout=timeout)
        except Exception:
            return False

    def record_crud(self, *, action: str, instance, actor=None, changes: dict | None = None):
        if not _audit_enabled():
            return
        obj_type = f"{instance.__class__.__module__}.{instance.__class__.__name__}"
        obj_id = getattr(instance, "pk", None)
        payload = {
            "action": action,
            "object_type": obj_type,
            "object_id": str(obj_id) if obj_id is not None else None,
            "changes": changes or {},
        }

        # Emit structured log asynchronously so network problems do not block the main Django process.
        # Use a daemon thread for best-effort, and log failures at DEBUG level.
        self._emit_async(
            "info", json.dumps({"event_type": "crud", **payload}), extra={"source": "audit", "audit": False}
        )

    def record_login(self, *, user=None, success=True, ip_address: str | None = None):
        if not _audit_enabled():
            return
        payload = {"user_id": getattr(user, "pk", None), "success": success, "ip": ip_address}
        self._emit_async(
            "info", json.dumps({"event_type": "login", **payload}), extra={"source": "audit", "audit": False}
        )

    def record_request(
        self, *, method: str, path: str, status_code: int | None = None, duration_ms: int | None = None, actor=None
    ):
        if not _audit_enabled():
            return
        payload = {"method": method, "path": path, "status_code": status_code, "duration_ms": duration_ms}
        self._emit_async(
            "info", json.dumps({"event_type": "request", **payload}), extra={"source": "audit", "audit": False}
        )

    def record_logentry(self, *, entry):
        """Forward an `auditlog.models.LogEntry` instance as a structured Loki/Audit event.

        Behavior changes:
        - If audits are disabled at runtime (`AUDIT_ENABLED=False`), attempt to delete the
          provided `LogEntry` instance so no persistent audit remains.
        - Otherwise, build a structured payload and emit it via the audit logger.
        """
        # If audit is disabled at runtime, attempt to remove the DB record to prevent persistence
        if not _audit_enabled():
            try:
                entry.delete()
                # Use logger attached to backend to record the deletion action
                logging.getLogger(__name__).debug(
                    "Audit disabled: removed LogEntry created during disabled state (id=%s)", getattr(entry, "pk", None)
                )
            except Exception:
                logging.getLogger(__name__).exception("Failed to remove LogEntry when audit disabled")
            return

        # Allow disabling of forwarding audit LogEntry events to Loki while still keeping audits in the DB.
        if not getattr(settings, "AUDIT_FORWARD_TO_LOKI", True):
            logging.getLogger(__name__).debug(
                "AUDIT_FORWARD_TO_LOKI is false: skipping forwarding to Loki for LogEntry(id=%s)",
                getattr(entry, "pk", None),
            )
            return

        # Enrich payload with actor username/email and human-friendly action codes
        payload = {
            "event_type": "auditlog",
            # Raw action value (integer enum)
            "action": entry.action,
            # Human friendly action code (C/U/D/A) and display name when available
            "action_code": None,
            "action_display": None,
            "object_type": f"{entry.content_type.app_label}.{entry.content_type.model}",
            "object_id": str(entry.object_pk) if entry.object_pk is not None else None,
            "actor": getattr(entry, "actor_id", None),
            "actor_username": None,
            "actor_email": getattr(entry, "actor_email", None),
            "changes": entry.changes if hasattr(entry, "changes") else {},
            "timestamp": entry.timestamp.isoformat() if hasattr(entry, "timestamp") else None,
        }

        # Attempt to resolve human-friendly action code/display from auditlog model
        try:
            from auditlog.models import LogEntry as AL

            action_map = {
                AL.Action.CREATE: "C",
                AL.Action.UPDATE: "U",
                AL.Action.DELETE: "D",
                AL.Action.ACCESS: "A",
            }
            payload["action_code"] = action_map.get(entry.action, str(entry.action))
            # If LogEntry provides a display helper, use it; otherwise fallback to str()
            try:
                payload["action_display"] = entry.get_action_display()
            except Exception:
                payload["action_display"] = str(entry.action)
        except Exception:
            # auditlog not available or introspection failed; best-effort
            try:
                payload["action_code"] = str(entry.action)
                payload["action_display"] = str(entry.action)
            except Exception:
                pass

        # Resolve actor username when actor object is available
        try:
            actor_obj = getattr(entry, "actor", None)
            if actor_obj is not None:
                payload["actor_username"] = getattr(actor_obj, "username", None) or (
                    getattr(actor_obj, "get_username", lambda: None)() if hasattr(actor_obj, "get_username") else None
                )
        except Exception:
            payload["actor_username"] = None

        # Tag audit-specific events so they can be filtered in Grafana/Loki
        self._emit_async("info", json.dumps(payload), extra={"source": "auditlog", "audit": True})
