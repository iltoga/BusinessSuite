from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta
from functools import wraps
from types import SimpleNamespace
from typing import Any, Callable, cast

import dramatiq
from django.utils import timezone
from dramatiq.middleware import CurrentMessage

QUEUE_REALTIME = "realtime"
QUEUE_DEFAULT = "default"
QUEUE_SCHEDULED = "scheduled"
QUEUE_LOW = "low"
QUEUE_DOC_CONVERSION = "doc_conversion"


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


def _build_task_context(*, max_retries: int) -> SimpleNamespace:
    retries_used = 0
    try:
        current_message = CurrentMessage.get_current_message()
        if current_message is not None:
            retries_used = int((current_message.options or {}).get("retries", 0) or 0)
    except Exception:
        retries_used = 0

    remaining = max(0, int(max_retries) - retries_used)
    return SimpleNamespace(retries=remaining)


def db_task(
    *dargs,
    name: str | None = None,
    retries: int = 0,
    retry_delay: int | float | None = None,
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
            context=context,
            queue=queue,
            priority=priority,
            **kwargs,
        )
        return cast(TaskCompat, decorator(direct_func))

    def decorator(func: Callable[..., Any]) -> TaskCompat:
        actor_name = name or f"{func.__module__}.{func.__name__}"

        @wraps(func)
        def _execute(*args, **inner_kwargs):
            if context:
                inner_kwargs = dict(inner_kwargs)
                inner_kwargs["task"] = _build_task_context(max_retries=retries)
            return func(*args, **inner_kwargs)

        actor_options: dict[str, Any] = {
            "actor_name": actor_name,
            "queue_name": queue,
            "max_retries": int(retries or 0),
        }
        if retry_delay is not None:
            actor_options["min_backoff"] = max(0, int(float(retry_delay) * 1000))
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
    retries: int = 0,
    retry_delay: int | float | None = None,
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
                context=context,
                queue=queue,
                priority=priority,
            )(func),
        )
        task_name = name or f"{func.__module__}.{func.__name__}"
        _PERIODIC_TASKS[task_name] = PeriodicTaskEntry(name=task_name, schedule=schedule, task=task)
        return task

    return decorator
