import threading

from core.services.logger_service import Logger
from core.telemetry.otlp_exporter import SpanContext, current_unix_nano, trace_exporter
from huey.contrib import djhuey
from huey.signals import (
    SIGNAL_CANCELED,
    SIGNAL_COMPLETE,
    SIGNAL_ERROR,
    SIGNAL_EXECUTING,
    SIGNAL_EXPIRED,
    SIGNAL_INTERRUPTED,
    SIGNAL_LOCKED,
    SIGNAL_RETRYING,
    SIGNAL_REVOKED,
)

logger = Logger.get_logger("telemetry.huey")

_active_task_spans: dict[str, tuple[SpanContext, str]] = {}
_active_task_lock = threading.Lock()


def _task_id(task) -> str:
    return str(getattr(task, "id", "unknown"))


def _task_name(task) -> str:
    return str(getattr(task, "name", task.__class__.__name__))


def _task_attributes(task, signal: str, error_type: str = "", error_message: str = "") -> dict[str, str | int]:
    attributes: dict[str, str | int] = {
        "huey.task.id": _task_id(task),
        "huey.task.name": _task_name(task),
        "huey.task.retries": int(getattr(task, "retries", 0) or 0),
        "huey.signal": signal,
    }

    eta = getattr(task, "eta", None)
    if eta is not None:
        attributes["huey.task.eta"] = str(eta)
    if error_type:
        attributes["error.type"] = error_type
    if error_message:
        attributes["error.message"] = error_message[:500]
    return attributes


def _start_task_span(task) -> None:
    if not trace_exporter.enabled:
        return
    task_key = _task_id(task)
    span_context = trace_exporter.start_server_span()
    start_unix_nano = current_unix_nano()
    with _active_task_lock:
        _active_task_spans[task_key] = (span_context, start_unix_nano)


def _end_task_span(task, signal: str, *, is_error: bool = False, error_type: str = "", error_message: str = "") -> None:
    if not trace_exporter.enabled:
        return

    task_key = _task_id(task)
    with _active_task_lock:
        span_context, start_unix_nano = _active_task_spans.pop(
            task_key,
            (trace_exporter.start_server_span(), current_unix_nano()),
        )

    trace_exporter.export_internal_span(
        span_context=span_context,
        span_name=f"huey:{_task_name(task)}",
        start_time_unix_nano=start_unix_nano,
        end_time_unix_nano=current_unix_nano(),
        attributes=_task_attributes(
            task,
            signal=signal,
            error_type=error_type,
            error_message=error_message,
        ),
        is_error=is_error,
    )


@djhuey.HUEY.signal(SIGNAL_EXECUTING)
def _on_task_executing(signal, task, *args, **kwargs):
    _start_task_span(task)


@djhuey.HUEY.signal(SIGNAL_COMPLETE)
def _on_task_complete(signal, task, *args, **kwargs):
    _end_task_span(task, signal=signal)


@djhuey.HUEY.signal(SIGNAL_ERROR)
def _on_task_error(signal, task, exc=None, *args, **kwargs):
    error_type = exc.__class__.__name__ if exc else "TaskExecutionError"
    error_message = str(exc) if exc else ""
    _end_task_span(task, signal=signal, is_error=True, error_type=error_type, error_message=error_message)


@djhuey.HUEY.signal(SIGNAL_INTERRUPTED, SIGNAL_CANCELED, SIGNAL_REVOKED, SIGNAL_EXPIRED, SIGNAL_LOCKED)
def _on_task_aborted(signal, task, *args, **kwargs):
    _end_task_span(task, signal=signal, is_error=True)


@djhuey.HUEY.signal(SIGNAL_RETRYING)
def _on_task_retrying(signal, task, *args, **kwargs):
    _end_task_span(task, signal=signal, is_error=True)


if trace_exporter.enabled:
    logger.info("Huey task tracing enabled")
