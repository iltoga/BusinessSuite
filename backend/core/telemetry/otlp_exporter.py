import os
import queue
import re
import secrets
import threading
import time
from dataclasses import dataclass
from typing import Any

import requests

from core.services.logger_service import Logger

_TRACEPARENT_RE = re.compile(r"^[\da-f]{2}-([\da-f]{32})-([\da-f]{16})-([\da-f]{2})$")
_DEFAULT_SCOPE_NAME = "revisbali.manual.backend"
_DEFAULT_EXPORT_TIMEOUT = 1.0


def _now_unix_nano() -> str:
    return str(time.time_ns())


def _parse_kv_csv(raw_value: str) -> dict[str, str]:
    parsed: dict[str, str] = {}
    for item in (raw_value or "").split(","):
        pair = item.strip()
        if not pair or "=" not in pair:
            continue
        key, value = pair.split("=", 1)
        key = key.strip()
        value = value.strip()
        if key:
            parsed[key] = value
    return parsed


def _to_otlp_value(value: Any) -> dict[str, Any]:
    if isinstance(value, bool):
        return {"boolValue": value}
    if isinstance(value, int):
        return {"intValue": str(value)}
    if isinstance(value, float):
        return {"doubleValue": value}
    return {"stringValue": str(value)}


def _to_otlp_attribute(key: str, value: Any) -> dict[str, Any]:
    return {"key": key, "value": _to_otlp_value(value)}


@dataclass(frozen=True)
class SpanContext:
    trace_id: str
    span_id: str
    trace_flags: str
    parent_span_id: str | None = None

    def traceparent(self) -> str:
        return f"00-{self.trace_id}-{self.span_id}-{self.trace_flags}"


class OtlpTraceExporter:
    def __init__(self) -> None:
        self.logger = Logger.get_logger("telemetry")

        traces_exporter = os.getenv("OTEL_TRACES_EXPORTER", "").strip().lower()
        self.endpoint = self._resolve_endpoint()
        self.enabled = bool(self.endpoint) and traces_exporter not in {"", "none"}

        self.export_timeout = self._resolve_export_timeout()
        self.service_name = os.getenv("OTEL_SERVICE_NAME", "backend")
        self.scope_name = os.getenv("OTEL_INSTRUMENTATION_SCOPE_NAME", _DEFAULT_SCOPE_NAME)

        self.resource_attributes = _parse_kv_csv(os.getenv("OTEL_RESOURCE_ATTRIBUTES", ""))
        # service.name must always be present for Grafana service maps/filters.
        self.resource_attributes.setdefault("service.name", self.service_name)

        self._request_headers = {"Content-Type": "application/json"}
        self._request_headers.update(_parse_kv_csv(os.getenv("OTEL_EXPORTER_OTLP_HEADERS", "")))

        self._queue: queue.SimpleQueue[dict[str, Any]] = queue.SimpleQueue()
        self._worker_started = False
        self._worker_lock = threading.Lock()
        self._last_error_log_ns = 0
        if self.enabled:
            self._start_worker()
        else:
            self.logger.info(
                "OTLP tracing disabled: set OTEL_TRACES_EXPORTER=otlp and OTEL_EXPORTER_OTLP_TRACES_ENDPOINT"
            )

    def _resolve_endpoint(self) -> str:
        traces_endpoint = (os.getenv("OTEL_EXPORTER_OTLP_TRACES_ENDPOINT") or "").strip()
        if traces_endpoint:
            return traces_endpoint

        base_endpoint = (os.getenv("OTEL_EXPORTER_OTLP_ENDPOINT") or "").strip().rstrip("/")
        if base_endpoint:
            return f"{base_endpoint}/v1/traces"
        return ""

    def _resolve_export_timeout(self) -> float:
        timeout_raw = (os.getenv("OTEL_EXPORTER_OTLP_TIMEOUT") or "").strip()
        if timeout_raw:
            try:
                timeout = float(timeout_raw)
                if timeout > 0:
                    return timeout
            except ValueError:
                pass
        return _DEFAULT_EXPORT_TIMEOUT

    def _start_worker(self) -> None:
        with self._worker_lock:
            if self._worker_started:
                return
            worker = threading.Thread(target=self._worker_loop, name="otlp-trace-exporter", daemon=True)
            worker.start()
            self._worker_started = True
            self.logger.info(f"OTLP tracing enabled, exporting to {self.endpoint}")

    def _worker_loop(self) -> None:
        while True:
            payload = self._queue.get()
            self._send(payload)

    def _send(self, payload: dict[str, Any]) -> None:
        try:
            response = requests.post(
                self.endpoint,
                json=payload,
                headers=self._request_headers,
                timeout=self.export_timeout,
            )
            if response.status_code >= 300:
                self._log_rate_limited_error(
                    f"OTLP export failed ({response.status_code}): {response.text[:600]}"
                )
        except Exception as exc:  # pylint: disable=broad-except
            self._log_rate_limited_error(f"OTLP export exception: {exc}")

    def _log_rate_limited_error(self, message: str) -> None:
        now = time.time_ns()
        # Avoid flooding logs if endpoint is down/misconfigured.
        if now - self._last_error_log_ns < 10_000_000_000:
            return
        self._last_error_log_ns = now
        self.logger.warning(message)

    def start_server_span(self, incoming_traceparent: str | None = None) -> SpanContext:
        if incoming_traceparent:
            parsed = _TRACEPARENT_RE.match(incoming_traceparent.strip().lower())
            if parsed:
                trace_id, parent_span_id, trace_flags = parsed.groups()
                return SpanContext(
                    trace_id=trace_id,
                    span_id=secrets.token_hex(8),
                    trace_flags=trace_flags,
                    parent_span_id=parent_span_id,
                )

        return SpanContext(
            trace_id=secrets.token_hex(16),
            span_id=secrets.token_hex(8),
            trace_flags="01",
            parent_span_id=None,
        )

    def export_http_server_span(
        self,
        *,
        span_context: SpanContext,
        span_name: str,
        start_time_unix_nano: str,
        end_time_unix_nano: str,
        attributes: dict[str, Any],
        status_code: int,
    ) -> None:
        if not self.enabled:
            return

        span_payload: dict[str, Any] = {
            "traceId": span_context.trace_id,
            "spanId": span_context.span_id,
            "name": span_name[:300],
            "kind": 2,  # SPAN_KIND_SERVER
            "startTimeUnixNano": start_time_unix_nano,
            "endTimeUnixNano": end_time_unix_nano,
            "attributes": [_to_otlp_attribute(key, value) for key, value in attributes.items()],
            "status": {"code": 2 if status_code >= 500 else 1},  # ERROR or OK
        }

        if span_context.parent_span_id:
            span_payload["parentSpanId"] = span_context.parent_span_id

        payload = {
            "resourceSpans": [
                {
                    "resource": {
                        "attributes": [
                            _to_otlp_attribute(key, value) for key, value in self.resource_attributes.items()
                        ]
                    },
                    "scopeSpans": [
                        {
                            "scope": {"name": self.scope_name},
                            "spans": [span_payload],
                        }
                    ],
                }
            ]
        }
        self._queue.put(payload)


trace_exporter = OtlpTraceExporter()


def current_unix_nano() -> str:
    return _now_unix_nano()

