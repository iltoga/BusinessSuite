import importlib
import json
import logging
import os
from datetime import datetime

from django.conf import settings

# Do NOT import Django models at module import time (prevents AppRegistryNotReady during logging configuration)
# Models are imported lazily inside backend methods to avoid importing them before Django apps are ready.


# Deprecated: Loki-specific handler removed in favor of OpenTelemetry OTLP handler.
# If you need to support the old logging_loki package, implement a separate adapter module.


# The old PersistentLokiBackend has been removed in favor of the
# PersistentOTLPBackend implementation below which uses the OTLP handler.


# --- OpenTelemetry-based fail-safe handler and backend (new) ---
class FailSafeOTLPHandler(logging.Handler):
    """Logging handler that attempts to export logs via OpenTelemetry OTLP and falls back to local file/console.

    The handler configures an OpenTelemetry LoggerProvider with an OTLP exporter
    (HTTP/protobuf) pointing to `OTLP_ENDPOINT` and uses the SDK's `LoggingHandler`
    as the primary sender. On any export error it writes to a fallback file and the console.
    """

    def __init__(self, endpoint: str | None = None, fallback_filename: str | None = None, level=logging.INFO):
        super().__init__(level)
        self.endpoint = endpoint or getattr(settings, "OTLP_ENDPOINT", "http://grafana-agent:4318/v1/logs")

        # Determine fallback filename safely
        if fallback_filename:
            self.fallback_filename = fallback_filename
        else:
            # Try to use logs/ in project root, or fall back to local dir
            base_dir = getattr(settings, "BASE_DIR", None)
            if base_dir:
                self.fallback_filename = os.path.join(str(base_dir), "logs", "audit_degraded.log")
            else:
                self.fallback_filename = "audit_degraded.log"

        # Ensure directory exists and initialize file handler
        try:
            log_dir = os.path.dirname(self.fallback_filename)
            if log_dir and not os.path.exists(log_dir):
                os.makedirs(log_dir, exist_ok=True)
            self._file_handler = logging.FileHandler(self.fallback_filename)
        except Exception:
            # If everything fails, use a NullHandler for the file part
            self._file_handler = logging.NullHandler()

        self._file_handler.setLevel(level)
        self._console = logging.StreamHandler()
        self._primary = None

        # Try to initialize OpenTelemetry Logging handler if available (use dynamic imports to avoid static errors)
        try:
            otel_logs = importlib.import_module("opentelemetry.sdk._logs")
            LoggerProvider = getattr(otel_logs, "LoggerProvider")
            BatchLogRecordProcessor = getattr(otel_logs, "BatchLogRecordProcessor")
            set_logger_provider = getattr(otel_logs, "set_logger_provider")
            LoggingHandler = getattr(otel_logs, "LoggingHandler")

            otlp_exporter_mod = importlib.import_module("opentelemetry.exporter.otlp.proto.http._log_exporter")
            OTLPLogExporter = getattr(otlp_exporter_mod, "OTLPLogExporter")

            res_mod = importlib.import_module("opentelemetry.sdk.resources")
            Resource = getattr(res_mod, "Resource")
            SERVICE_NAME = getattr(res_mod, "SERVICE_NAME")

            resource = Resource.create({SERVICE_NAME: getattr(settings, "OTEL_SERVICE_NAME", "business_suite")})
            lp = LoggerProvider(resource=resource)
            exporter = OTLPLogExporter(endpoint=self.endpoint, timeout=float(getattr(settings, "OTLP_TIMEOUT", 5.0)))
            lp.add_log_record_processor(BatchLogRecordProcessor(exporter))
            set_logger_provider(lp)

            # The LoggingHandler integrates Python logging with OpenTelemetry
            self._primary = LoggingHandler(level=level, logger_provider=lp)
        except Exception:
            # If OpenTelemetry classes are not available or initialization fails, fall back later in emit
            self._primary = None

    def emit(self, record: logging.LogRecord) -> None:
        try:
            if self._primary:
                # Delegate to the OpenTelemetry logging handler
                self._primary.emit(record)
                return
            raise RuntimeError("OpenTelemetry LoggingHandler not initialized")
        except Exception as exc:  # pragma: no cover - network/fallback behavior
            try:
                msg = self.format(record)
                fallback_msg = f"[OTLP_SEND_FAILED] {datetime.utcnow().isoformat()} {msg} | exc={exc}"
                self._file_handler.emit(
                    logging.LogRecord(
                        record.name, record.levelno, record.pathname, record.lineno, fallback_msg, (), None
                    )
                )
            except Exception:
                # Last resort: console
                self._console.emit(record)


class PersistentOTLPBackend:
    """A persistent audit backend that stores audit events to the DB and emits a structured log via OpenTelemetry.

    Retains the same behavior as the previous PersistentLokiBackend but emits structured JSON
    to the `audit` logger which is handled by `FailSafeOTLPHandler`.
    """

    def __init__(self, logger_name: str = "audit"):
        self.logger = logging.getLogger(logger_name)

    def record_crud(self, *, action: str, instance, actor=None, changes: dict | None = None):
        obj_type = f"{instance.__class__.__module__}.{instance.__class__.__name__}"
        obj_id = getattr(instance, "pk", None)
        payload = {
            "action": action,
            "object_type": obj_type,
            "object_id": str(obj_id) if obj_id is not None else None,
            "changes": changes or {},
        }
        # Persist to DB (lazy import to avoid AppRegistryNotReady at module import)
        try:
            try:
                from core.models.audit import CRUDEvent
            except Exception:  # Apps not ready or import error
                CRUDEvent = None
            if CRUDEvent is not None:
                CRUDEvent.objects.create(
                    action=action,
                    object_type=obj_type,
                    object_id=str(obj_id) if obj_id is not None else None,
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    data=payload,
                    source="django",
                )
        except Exception as exc:  # pragma: no cover - DB error guard
            self.logger.warning("Failed to persist CRUDEvent to DB: %s", exc)

        # Emit structured log
        self.logger.info(json.dumps({"event_type": "crud", **payload}), extra={"source": "audit"})

    def record_login(self, *, user=None, success=True, ip_address: str | None = None):
        payload = {"user_id": getattr(user, "pk", None), "success": success, "ip": ip_address}
        try:
            try:
                from core.models.audit import LoginEvent
            except Exception:
                LoginEvent = None
            if LoginEvent is not None:
                LoginEvent.objects.create(
                    actor=user if getattr(user, "is_authenticated", False) else None,
                    data=payload,
                    source="django",
                    success=success,
                    ip_address=ip_address,
                )
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Failed to persist LoginEvent: %s", exc)
        self.logger.info(json.dumps({"event_type": "login", **payload}), extra={"source": "audit"})

    def record_request(
        self, *, method: str, path: str, status_code: int | None = None, duration_ms: int | None = None, actor=None
    ):
        payload = {"method": method, "path": path, "status_code": status_code, "duration_ms": duration_ms}
        try:
            try:
                from core.models.audit import RequestEvent
            except Exception:
                RequestEvent = None
            if RequestEvent is not None:
                RequestEvent.objects.create(
                    actor=actor if getattr(actor, "is_authenticated", False) else None,
                    data=payload,
                    source="django",
                    method=method,
                    path=path,
                    status_code=status_code,
                    duration_ms=duration_ms,
                )
        except Exception as exc:  # pragma: no cover
            self.logger.warning("Failed to persist RequestEvent: %s", exc)
        self.logger.info(json.dumps({"event_type": "request", **payload}), extra={"source": "audit"})
