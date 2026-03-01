from __future__ import annotations

import asyncio
from functools import wraps
from typing import Any, Callable

from core.services.logger_service import Logger
from core.telemetry.otlp_exporter import SpanContext, current_unix_nano, trace_exporter

logger = Logger.get_logger("telemetry.pgqueue")


def instrument_entrypoint(entrypoint: str, func: Callable[..., Any]) -> Callable[..., Any]:
    if not trace_exporter.enabled:
        return func

    if asyncio.iscoroutinefunction(func):

        @wraps(func)
        async def _async_wrapped(*args: Any, **kwargs: Any) -> Any:
            span_context: SpanContext = trace_exporter.start_server_span()
            start = current_unix_nano()
            try:
                result = await func(*args, **kwargs)
            except Exception as exc:
                trace_exporter.export_internal_span(
                    span_context=span_context,
                    span_name=f"pgqueue:{entrypoint}",
                    start_time_unix_nano=start,
                    end_time_unix_nano=current_unix_nano(),
                    attributes={
                        "pgqueue.entrypoint": entrypoint,
                        "error.type": type(exc).__name__,
                        "error.message": str(exc)[:500],
                    },
                    is_error=True,
                )
                raise

            trace_exporter.export_internal_span(
                span_context=span_context,
                span_name=f"pgqueue:{entrypoint}",
                start_time_unix_nano=start,
                end_time_unix_nano=current_unix_nano(),
                attributes={"pgqueue.entrypoint": entrypoint},
                is_error=False,
            )
            return result

        return _async_wrapped

    @wraps(func)
    def _sync_wrapped(*args: Any, **kwargs: Any) -> Any:
        span_context = trace_exporter.start_server_span()
        start = current_unix_nano()
        try:
            result = func(*args, **kwargs)
        except Exception as exc:
            trace_exporter.export_internal_span(
                span_context=span_context,
                span_name=f"pgqueue:{entrypoint}",
                start_time_unix_nano=start,
                end_time_unix_nano=current_unix_nano(),
                attributes={
                    "pgqueue.entrypoint": entrypoint,
                    "error.type": type(exc).__name__,
                    "error.message": str(exc)[:500],
                },
                is_error=True,
            )
            raise

        trace_exporter.export_internal_span(
            span_context=span_context,
            span_name=f"pgqueue:{entrypoint}",
            start_time_unix_nano=start,
            end_time_unix_nano=current_unix_nano(),
            attributes={"pgqueue.entrypoint": entrypoint},
            is_error=False,
        )
        return result

    return _sync_wrapped


if trace_exporter.enabled:
    logger.info("PgQueuer entrypoint tracing enabled")
