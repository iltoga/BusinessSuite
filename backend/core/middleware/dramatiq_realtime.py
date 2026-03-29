"""
FILE_ROLE: Middleware for realtime Dramatiq tracing or event handling.

KEY_COMPONENTS:
- RealtimeJobMiddleware: Module symbol.

INTERACTIONS:
- Depends on: core.models, core.services, Django signal machinery, or middleware hooks as appropriate.

AI_GUIDELINES:
- Keep this module focused on framework integration and small hook functions.
- Do not move domain orchestration here when a service already owns the workflow.
"""

import logging
from typing import Any, Dict

from core.services.realtime_dispatcher import RealtimeEventDispatcherService
from dramatiq import Message
from dramatiq.middleware import Middleware

logger = logging.getLogger(__name__)


class RealtimeJobMiddleware(Middleware):
    """
    Dramatiq middleware that automatically publishes task lifecycle events
    (enqueue, process, success, failure) to a multiplexed user-specific Redis SSE Stream.

    This operates generically. It only fires if the task was dispatched with
    the relevant correlation options:
    `task.send_with_options(args=(...), options={"realtime_user_id": 1, "realtime_job_id": "uuid"})`
    """

    def _extract_realtime_metadata(self, message: Message) -> Dict[str, Any]:
        options = getattr(message, "options", {}) or {}
        user_id = options.get("realtime_user_id")
        job_id = options.get("realtime_job_id")
        return {"user_id": user_id, "job_id": job_id}

    def after_enqueue(self, broker, message, delay):
        meta = self._extract_realtime_metadata(message)
        if meta["user_id"] and meta["job_id"]:
            RealtimeEventDispatcherService.publish_job_update(
                user_id=meta["user_id"],
                job_id=meta["job_id"],
                status="queued",
                progress=0,
                payload={"message_id": message.message_id},
            )

    def before_process_message(self, broker, message):
        meta = self._extract_realtime_metadata(message)
        if meta["user_id"] and meta["job_id"]:
            RealtimeEventDispatcherService.publish_job_update(
                user_id=meta["user_id"],
                job_id=meta["job_id"],
                status="processing",
                progress=5,
                payload={"message_id": message.message_id},
            )

    def after_process_message(self, broker, message, *, result=None, exception=None):
        meta = self._extract_realtime_metadata(message)
        if not meta["user_id"] or not meta["job_id"]:
            return

        if exception is not None:
            # Task explicitly failed (raised exception)
            RealtimeEventDispatcherService.publish_job_update(
                user_id=meta["user_id"],
                job_id=meta["job_id"],
                status="failed",
                progress=100,
                payload={"error": str(exception)},
            )
        else:
            # Task succeeded without exceptions.
            RealtimeEventDispatcherService.publish_job_update(
                user_id=meta["user_id"],
                job_id=meta["job_id"],
                status="completed",
                progress=100,
            )
