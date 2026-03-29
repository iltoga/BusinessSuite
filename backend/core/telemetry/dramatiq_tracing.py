"""
FILE_ROLE: Integrates Dramatiq middleware with the backend tracing exporter.

KEY_COMPONENTS:
- DramatiqTracingMiddleware: Captures Dramatiq message spans and exports them through the OTLP exporter.

INTERACTIONS:
- Depends on: core.telemetry.otlp_exporter, core.services.logger_service.Logger, dramatiq.middleware.Middleware.

AI_GUIDELINES:
- Keep the middleware lightweight and defer span export details to the shared OTLP exporter.
- Do not add task business logic here; this module should only observe and report execution metadata.
"""

from __future__ import annotations

import threading
from typing import Any

from core.services.logger_service import Logger
from core.telemetry.otlp_exporter import SpanContext, current_unix_nano, trace_exporter
from dramatiq.middleware import Middleware

logger = Logger.get_logger("telemetry.dramatiq")

_active_spans: dict[str, tuple[SpanContext, str]] = {}
_lock = threading.Lock()


class DramatiqTracingMiddleware(Middleware):
    def before_process_message(self, broker, message) -> None:  # noqa: ANN001
        if not trace_exporter.enabled:
            return
        message_id = str(getattr(message, "message_id", "unknown"))
        span_context = trace_exporter.start_server_span()
        with _lock:
            _active_spans[message_id] = (span_context, current_unix_nano())

    def after_process_message(self, broker, message, *, result=None, exception=None) -> None:  # noqa: ANN001
        self._finish(message, exception=exception)

    def after_skip_message(self, broker, message) -> None:  # noqa: ANN001
        self._finish(message, exception=RuntimeError("message skipped"))

    def after_nack(self, broker, message) -> None:  # noqa: ANN001
        self._finish(message, exception=RuntimeError("message nacked"))

    def _finish(self, message, *, exception: BaseException | None) -> None:  # noqa: ANN001
        if not trace_exporter.enabled:
            return

        message_id = str(getattr(message, "message_id", "unknown"))
        actor_name = str(getattr(message, "actor_name", "unknown"))
        with _lock:
            span_context, start_unix_nano = _active_spans.pop(
                message_id,
                (trace_exporter.start_server_span(), current_unix_nano()),
            )

        attributes: dict[str, Any] = {
            "dramatiq.message.id": message_id,
            "dramatiq.actor": actor_name,
            "dramatiq.queue": str(getattr(message, "queue_name", "")),
            "dramatiq.options": str(getattr(message, "options", {}) or {}),
        }
        if exception is not None:
            attributes["error.type"] = exception.__class__.__name__
            attributes["error.message"] = str(exception)[:500]

        trace_exporter.export_internal_span(
            span_context=span_context,
            span_name=f"dramatiq:{actor_name}",
            start_time_unix_nano=start_unix_nano,
            end_time_unix_nano=current_unix_nano(),
            attributes=attributes,
            is_error=exception is not None,
        )


if trace_exporter.enabled:
    logger.info("Dramatiq task tracing enabled")
