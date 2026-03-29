"""
FILE_ROLE: Django management command for the core app.

KEY_COMPONENTS:
- SchedulerLock: Module symbol.
- Command: Module symbol.

INTERACTIONS:
- Depends on: core app schema/runtime machinery and adjacent services imported by this module.

AI_GUIDELINES:
- Keep command logic thin and delegate real work to services when possible.
- Keep migrations schema-only and reversible; do not add runtime business logic here.
"""

from __future__ import annotations

import signal
import time
import uuid
from dataclasses import dataclass

from core.services.logger_service import Logger
from core.services.redis_client import get_redis_client
from core.tasks.runtime import iter_periodic_tasks
from django.conf import settings
from django.core.management.base import BaseCommand
from django.utils import timezone
from redis.exceptions import RedisError

logger = Logger.get_logger(__name__)


@dataclass
class SchedulerLock:
    key: str
    token: str
    ttl_seconds: int


class Command(BaseCommand):
    help = "Run periodic task scheduler for Dramatiq actors."

    def add_arguments(self, parser):
        parser.add_argument("--tick-seconds", type=float, default=1.0)
        parser.add_argument(
            "--lock-key",
            type=str,
            default=str(getattr(settings, "DRAMATIQ_SCHEDULER_LOCK_KEY", "dramatiq:scheduler:lock")),
        )
        parser.add_argument(
            "--lock-ttl-seconds",
            type=int,
            default=int(getattr(settings, "DRAMATIQ_SCHEDULER_LOCK_TTL_SECONDS", 30)),
        )

    def handle(self, *args, **options):
        from business_suite import dramatiq as _dramatiq  # noqa: F401

        tick_seconds = max(0.2, float(options["tick_seconds"]))
        lock = SchedulerLock(
            key=str(options["lock_key"]),
            token=uuid.uuid4().hex,
            ttl_seconds=max(5, int(options["lock_ttl_seconds"])),
        )

        self._running = True
        signal.signal(signal.SIGINT, self._stop)
        signal.signal(signal.SIGTERM, self._stop)

        logger.info("Starting Dramatiq scheduler loop")

        redis_client = self._new_redis_client()
        last_minute = None

        while self._running:
            try:
                if not self._acquire_or_refresh_lock(redis_client, lock):
                    time.sleep(tick_seconds)
                    continue

                current_time = timezone.localtime(timezone.now()).replace(second=0, microsecond=0)
                if current_time != last_minute:
                    self._run_due_tasks(redis_client, now=current_time)
                    last_minute = current_time

                time.sleep(tick_seconds)
            except RedisError as exc:
                logger.warning("Scheduler Redis error, retrying: %s", exc)
                time.sleep(max(1.0, tick_seconds))
                redis_client = self._new_redis_client()
            except Exception:
                logger.exception("Unhandled scheduler loop error")
                time.sleep(max(1.0, tick_seconds))

        try:
            self._release_lock(redis_client, lock)
        except RedisError as exc:
            logger.warning("Scheduler lock release skipped due to Redis error: %s", exc)
        logger.info("Dramatiq scheduler stopped")

    def _new_redis_client(self):
        # Slightly higher timeout for long-running scheduler process to avoid
        # unnecessary exits on transient Redis/network stalls.
        return get_redis_client(socket_timeout=10, socket_connect_timeout=5)

    def _run_due_tasks(self, redis_client, *, now):
        periodic_tasks = iter_periodic_tasks()
        if not periodic_tasks:
            return

        logger.debug("Evaluating %s periodic tasks at %s", len(periodic_tasks), now.isoformat())

        for entry in periodic_tasks:
            if not entry.schedule.is_due(now):
                continue

            dedupe_key = f"dramatiq:scheduler:dedupe:{entry.name}:{now.isoformat()}"
            if not redis_client.set(dedupe_key, "1", nx=True, ex=120):
                continue

            entry.task.delay()
            logger.info("Scheduled periodic task %s", entry.name)

    def _acquire_or_refresh_lock(self, redis_client, lock: SchedulerLock) -> bool:
        if redis_client.set(lock.key, lock.token, nx=True, ex=lock.ttl_seconds):
            return True

        current = redis_client.get(lock.key)
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        if current != lock.token:
            return False

        redis_client.expire(lock.key, lock.ttl_seconds)
        return True

    def _release_lock(self, redis_client, lock: SchedulerLock) -> None:
        current = redis_client.get(lock.key)
        if isinstance(current, bytes):
            current = current.decode("utf-8")
        if current == lock.token:
            redis_client.delete(lock.key)

    def _stop(self, signum, frame):
        self._running = False
