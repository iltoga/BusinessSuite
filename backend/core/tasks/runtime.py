from __future__ import annotations

import logging
import random
from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from types import SimpleNamespace
from typing import Any, Callable, cast

import dramatiq
from django.utils import timezone
from dramatiq.middleware import CurrentMessage, TimeLimitExceeded

QUEUE_REALTIME = "realtime"
QUEUE_DEFAULT = "default"
QUEUE_SCHEDULED = "scheduled"
QUEUE_LOW = "low"
QUEUE_DOC_CONVERSION = "doc_conversion"

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class TaskPolicy:
    retries: int = 0
    retry_delay_ms: int | None = None
    max_backoff_ms: int | None = None
    retry_jitter_ms: int | None = None
    time_limit_ms: int | None = None


QUEUE_TASK_POLICY_DEFAULTS: dict[str, TaskPolicy] = {
    QUEUE_REALTIME: TaskPolicy(
        retries=2,
        retry_delay_ms=10_000,
        max_backoff_ms=45_000,
        retry_jitter_ms=5_000,
        time_limit_ms=150_000,
    ),
    QUEUE_DEFAULT: TaskPolicy(
        retries=1,
        retry_delay_ms=15_000,
        max_backoff_ms=90_000,
        retry_jitter_ms=5_000,
        time_limit_ms=300_000,
    ),
    QUEUE_LOW: TaskPolicy(
        retries=1,
        retry_delay_ms=30_000,
        max_backoff_ms=180_000,
        retry_jitter_ms=10_000,
        time_limit_ms=300_000,
    ),
    QUEUE_DOC_CONVERSION: TaskPolicy(
        retries=3,
        retry_delay_ms=15_000,
        max_backoff_ms=180_000,
        retry_jitter_ms=10_000,
        time_limit_ms=420_000,
    ),
}


@dataclass(frozen=True)
class CrontabSchedule:
    minute: str | int = "*"
    hour: str | int = "*"
    day: str | int = "*"
    month: str | int = "*"
    day_of_week: str | int = "*"

    def is_due(self, at: datetime) -> bool:
        return (
            _match_field(at.minute, self.minute, minimum=0, maximum=59)
            and _match_field(at.hour, self.hour, minimum=0, maximum=23)
            and _match_field(at.day, self.day, minimum=1, maximum=31)
            and _match_field(at.month, self.month, minimum=1, maximum=12)
            and _match_field(_cron_weekday(at), self.day_of_week, minimum=0, maximum=7)
        )


@dataclass(frozen=True)
class PeriodicTaskEntry:
    name: str
    schedule: CrontabSchedule
    task: "TaskCompat"


_PERIODIC_TASKS: dict[str, PeriodicTaskEntry] = {}


def _cron_weekday(value: datetime) -> int:
    # Python weekday: Monday=0...Sunday=6. Cron: Sunday=0/7, Monday=1.
    py = value.weekday()
    return 0 if py == 6 else py + 1


def _match_field(value: int, expression: str | int, *, minimum: int, maximum: int) -> bool:
    if isinstance(expression, int):
        return value == expression

    expr = str(expression).strip()
    if not expr or expr == "*":
        return True

    parts = [part.strip() for part in expr.split(",") if part.strip()]
    for part in parts:
        if _match_part(value, part, minimum=minimum, maximum=maximum):
            return True
    return False


def _match_part(value: int, expression: str, *, minimum: int, maximum: int) -> bool:
    if expression == "*":
        return True

    if expression.startswith("*/"):
        step = int(expression[2:])
        if step <= 0:
            return False
        return (value - minimum) % step == 0

    if "/" in expression and "-" in expression:
        range_expr, step_expr = expression.split("/", 1)
        start_expr, end_expr = range_expr.split("-", 1)
        start = int(start_expr)
        end = int(end_expr)
        step = int(step_expr)
        if step <= 0:
            return False
        return start <= value <= end and (value - start) % step == 0

    if "-" in expression:
        start_expr, end_expr = expression.split("-", 1)
        start = int(start_expr)
        end = int(end_expr)
        return start <= value <= end

    try:
        parsed = int(expression)
    except ValueError:
        return False

    if parsed == 7 and maximum == 7:
        parsed = 0
    return parsed == value


def crontab(
    *,
    minute: str | int = "*",
    hour: str | int = "*",
    day: str | int = "*",
    month: str | int = "*",
    day_of_week: str | int = "*",
) -> CrontabSchedule:
    return CrontabSchedule(minute=minute, hour=hour, day=day, month=month, day_of_week=day_of_week)


def iter_periodic_tasks() -> tuple[PeriodicTaskEntry, ...]:
    return tuple(_PERIODIC_TASKS.values())


def reset_periodic_registry() -> None:
    _PERIODIC_TASKS.clear()


class TaskCompat:
    def __init__(self, *, actor: dramatiq.Actor, func: Callable[..., Any], context_enabled: bool):
        self._actor = actor
        self._func = func
        self._context_enabled = context_enabled
        self.__name__ = getattr(func, "__name__", actor.actor_name)
        self.__doc__ = getattr(func, "__doc__", "")

    def __call__(self, *args, **kwargs):
        return self.delay(*args, **kwargs)

    def delay(self, *args, **kwargs):
        return self._actor.send(*args, **kwargs)

    def send(self, *args, **kwargs):
        return self._actor.send(*args, **kwargs)

    def schedule(
        self,
        args: tuple[Any, ...] | list[Any] | None = None,
        kwargs: dict[str, Any] | None = None,
        *,
        delay: float | int | timedelta | None = None,
        eta: datetime | None = None,
    ):
        options: dict[str, Any] = {}
        if delay is not None:
            options["delay"] = _coerce_delay_ms(delay)
        elif eta is not None:
            options["delay"] = _eta_to_delay_ms(eta)

        return self._actor.send_with_options(
            args=tuple(args or ()),
            kwargs=dict(kwargs or {}),
            **options,
        )

    def call_local(self, *args, **kwargs):
        if self._context_enabled and "task" not in kwargs:
            kwargs["task"] = None
        return self._func(*args, **kwargs)

    @property
    def func(self):
        return self._func

    @property
    def actor(self) -> dramatiq.Actor:
        return self._actor

    def __getattr__(self, item: str):
        return getattr(self._actor, item)


def _coerce_delay_ms(value: float | int | timedelta) -> int:
    if isinstance(value, timedelta):
        seconds = value.total_seconds()
    else:
        seconds = float(value)
    return max(0, int(seconds * 1000))


def _eta_to_delay_ms(eta: datetime) -> int:
    target = eta
    if timezone.is_naive(target):
        target = timezone.make_aware(target, timezone.get_current_timezone())
    delta = target - timezone.now()
    return _coerce_delay_ms(delta)


def _current_retries_used() -> int:
    retries_used = 0
    try:
        current_message = CurrentMessage.get_current_message()
        if current_message is not None:
            retries_used = int((current_message.options or {}).get("retries", 0) or 0)
    except Exception:
        retries_used = 0

    return retries_used


def _build_task_context(
    *,
    actor_name: str,
    queue_name: str,
    policy: TaskPolicy,
) -> SimpleNamespace:
    retries_used = _current_retries_used()

    remaining = max(0, int(policy.retries) - retries_used)
    return SimpleNamespace(
        retries=remaining,
        retries_used=retries_used,
        attempt=retries_used + 1,
        max_retries=int(policy.retries),
        actor_name=actor_name,
        queue_name=queue_name,
        retry_delay_ms=policy.retry_delay_ms,
        max_backoff_ms=policy.max_backoff_ms,
        retry_jitter_ms=policy.retry_jitter_ms,
        time_limit_ms=policy.time_limit_ms,
    )


def _resolve_policy(
    *,
    queue: str,
    queue_defaults: bool,
    retries: int | None,
    retry_delay: int | float | None,
    max_backoff_ms: int | None,
    retry_jitter_ms: int | None,
    time_limit_ms: int | None,
) -> TaskPolicy:
    defaults = QUEUE_TASK_POLICY_DEFAULTS.get(queue, TaskPolicy()) if queue_defaults else TaskPolicy()
    return TaskPolicy(
        retries=int(defaults.retries if retries is None else retries),
        retry_delay_ms=(defaults.retry_delay_ms if retry_delay is None else max(0, int(float(retry_delay) * 1000))),
        max_backoff_ms=defaults.max_backoff_ms if max_backoff_ms is None else max(0, int(max_backoff_ms)),
        retry_jitter_ms=defaults.retry_jitter_ms if retry_jitter_ms is None else max(0, int(retry_jitter_ms)),
        time_limit_ms=defaults.time_limit_ms if time_limit_ms is None else max(0, int(time_limit_ms)),
    )


def _normalize_throws(
    throws: type[BaseException] | tuple[type[BaseException], ...] | None,
) -> tuple[type[BaseException], ...]:
    if throws is None:
        return ()
    if isinstance(throws, tuple):
        return throws
    return (throws,)


def _is_transient_external_failure(exc: BaseException) -> bool:
    if isinstance(exc, TimeLimitExceeded):
        return True
    if isinstance(exc, (TimeoutError, ConnectionError)):
        return True

    error_code = str(getattr(exc, "error_code", "") or "").strip().lower()
    if error_code in {"timeout", "connection_error", "rate_limit", "internal_server", "status_error"}:
        return True

    status_code = getattr(exc, "status_code", None)
    if isinstance(status_code, int) and status_code >= 500:
        return True

    return False


def retry_on_transient_external_failure(_retries_so_far: int, exc: BaseException) -> bool:
    return _is_transient_external_failure(exc)


def _compute_retry_delay_ms(*, retries_used: int, policy: TaskPolicy) -> int:
    base_delay = max(0, int(policy.retry_delay_ms or 0))
    if base_delay <= 0:
        return 0

    delay = base_delay * (2 ** max(0, retries_used))
    max_backoff_ms = policy.max_backoff_ms
    if max_backoff_ms is not None:
        delay = min(delay, max_backoff_ms)

    jitter_ms = max(0, int(policy.retry_jitter_ms or 0))
    if jitter_ms > 0:
        upper_bound = delay + jitter_ms
        if max_backoff_ms is not None:
            upper_bound = min(max_backoff_ms, upper_bound)
        delay = random.randint(delay, max(delay, upper_bound))

    return delay


def _should_retry_exception(
    *,
    retries_used: int,
    max_retries: int,
    throws: tuple[type[BaseException], ...],
    retry_when: Callable[[int, BaseException], bool] | None,
    exc: BaseException,
) -> bool:
    if max_retries <= 0 or retries_used >= max_retries:
        return False
    if throws and isinstance(exc, throws):
        return False
    if retry_when is not None:
        return bool(retry_when(retries_used, exc))
    return True


def _build_actor_retry_when(
    *,
    max_retries: int,
    throws: tuple[type[BaseException], ...],
    retry_when: Callable[[int, BaseException], bool] | None,
) -> Callable[[int, BaseException], bool]:
    def _actor_retry_when(retries_so_far: int, exc: BaseException) -> bool:
        if retries_so_far >= max_retries:
            return False
        if isinstance(exc, dramatiq.Retry):
            return True
        if throws and isinstance(exc, throws):
            return False
        if retry_when is not None:
            return bool(retry_when(retries_so_far, exc))
        return True

    return _actor_retry_when


def db_task(
    *dargs,
    name: str | None = None,
    retries: int | None = None,
    retry_delay: int | float | None = None,
    max_backoff_ms: int | None = None,
    retry_jitter_ms: int | None = None,
    time_limit_ms: int | None = None,
    queue_defaults: bool = False,
    retry_when: Callable[[int, BaseException], bool] | None = None,
    throws: type[BaseException] | tuple[type[BaseException], ...] | None = None,
    context: bool = False,
    queue: str = QUEUE_DEFAULT,
    priority: int | None = None,
    **kwargs,
):
    if dargs and callable(dargs[0]):
        direct_func = cast(Callable[..., Any], dargs[0])
        decorator = db_task(
            name=name,
            retries=retries,
            retry_delay=retry_delay,
            max_backoff_ms=max_backoff_ms,
            retry_jitter_ms=retry_jitter_ms,
            time_limit_ms=time_limit_ms,
            queue_defaults=queue_defaults,
            retry_when=retry_when,
            throws=throws,
            context=context,
            queue=queue,
            priority=priority,
            **kwargs,
        )
        return cast(TaskCompat, decorator(direct_func))

    def decorator(func: Callable[..., Any]) -> TaskCompat:
        actor_name = name or f"{func.__module__}.{func.__name__}"
        policy = _resolve_policy(
            queue=queue,
            queue_defaults=queue_defaults,
            retries=retries,
            retry_delay=retry_delay,
            max_backoff_ms=max_backoff_ms,
            retry_jitter_ms=retry_jitter_ms,
            time_limit_ms=time_limit_ms,
        )
        throws_tuple = _normalize_throws(throws)
        actor_retry_when = _build_actor_retry_when(
            max_retries=policy.retries,
            throws=throws_tuple,
            retry_when=retry_when,
        )

        @wraps(func)
        def _execute(*args, **inner_kwargs):
            task_context = None
            if context:
                inner_kwargs = dict(inner_kwargs)
                task_context = _build_task_context(actor_name=actor_name, queue_name=queue, policy=policy)
                inner_kwargs["task"] = task_context

            if policy.retries > 0 or policy.time_limit_ms is not None:
                if task_context is None:
                    task_context = _build_task_context(actor_name=actor_name, queue_name=queue, policy=policy)
                logger.info(
                    "Starting task actor=%s queue=%s attempt=%s/%s time_limit_ms=%s retry_delay_ms=%s max_backoff_ms=%s retry_jitter_ms=%s",
                    actor_name,
                    queue,
                    task_context.attempt,
                    max(1, task_context.max_retries + 1),
                    policy.time_limit_ms,
                    policy.retry_delay_ms,
                    policy.max_backoff_ms,
                    policy.retry_jitter_ms,
                )

            try:
                return func(*args, **inner_kwargs)
            except dramatiq.Retry:
                raise
            except Exception as exc:
                retries_used = _current_retries_used()
                if _should_retry_exception(
                    retries_used=retries_used,
                    max_retries=policy.retries,
                    throws=throws_tuple,
                    retry_when=retry_when,
                    exc=exc,
                ):
                    retry_delay_ms = _compute_retry_delay_ms(retries_used=retries_used, policy=policy)
                    logger.warning(
                        "Retryable task failure actor=%s queue=%s attempt=%s/%s retry_in_ms=%s error_type=%s error=%s",
                        actor_name,
                        queue,
                        retries_used + 1,
                        max(1, policy.retries + 1),
                        retry_delay_ms,
                        type(exc).__name__,
                        exc,
                    )
                    raise dramatiq.Retry(delay=retry_delay_ms) from exc

                if isinstance(exc, TimeLimitExceeded):
                    logger.error(
                        "Task time limit exceeded actor=%s queue=%s attempt=%s/%s time_limit_ms=%s",
                        actor_name,
                        queue,
                        retries_used + 1,
                        max(1, policy.retries + 1),
                        policy.time_limit_ms,
                    )
                raise

        actor_options: dict[str, Any] = {
            "actor_name": actor_name,
            "queue_name": queue,
            "max_retries": int(policy.retries),
            "retry_when": actor_retry_when,
        }
        if policy.retry_delay_ms is not None:
            actor_options["min_backoff"] = policy.retry_delay_ms
        if policy.max_backoff_ms is not None:
            actor_options["max_backoff"] = policy.max_backoff_ms
        if policy.time_limit_ms is not None:
            actor_options["time_limit"] = policy.time_limit_ms
        if throws_tuple:
            actor_options["throws"] = throws_tuple
        if priority is not None:
            actor_options["priority"] = int(priority)

        actor = dramatiq.actor(**actor_options)(_execute)
        return TaskCompat(actor=actor, func=func, context_enabled=context)

    return decorator


def db_periodic_task(
    schedule: CrontabSchedule,
    *,
    name: str | None = None,
    queue: str = QUEUE_SCHEDULED,
    retries: int | None = None,
    retry_delay: int | float | None = None,
    max_backoff_ms: int | None = None,
    retry_jitter_ms: int | None = None,
    time_limit_ms: int | None = None,
    queue_defaults: bool = False,
    retry_when: Callable[[int, BaseException], bool] | None = None,
    throws: type[BaseException] | tuple[type[BaseException], ...] | None = None,
    context: bool = False,
    priority: int | None = None,
):
    def decorator(func: Callable[..., Any]) -> TaskCompat:
        task = cast(
            TaskCompat,
            db_task(
                name=name,
                retries=retries,
                retry_delay=retry_delay,
                max_backoff_ms=max_backoff_ms,
                retry_jitter_ms=retry_jitter_ms,
                time_limit_ms=time_limit_ms,
                queue_defaults=queue_defaults,
                retry_when=retry_when,
                throws=throws,
                context=context,
                queue=queue,
                priority=priority,
            )(func),
        )
        task_name = name or f"{func.__module__}.{func.__name__}"
        _PERIODIC_TASKS[task_name] = PeriodicTaskEntry(name=task_name, schedule=schedule, task=task)
        return task

    return decorator
