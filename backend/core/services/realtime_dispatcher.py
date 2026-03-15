import logging
from typing import Any, Dict, Optional

from core.services.redis_streams import publish_stream_event, stream_user_key

logger = logging.getLogger(__name__)

class RealtimeEventDispatcherService:
    """
    A generic service to dispatch real-time events to a specific user's Redis Stream.
    This replaces individual, per-task SSE endpoints with a unified global event bus.
    """

    @classmethod
    def publish_event(
        cls,
        user_id: int | str,
        event: str,
        payload: Dict[str, Any],
        status: str = "info",
        job_id: Optional[str] = None,
        correlation_id: Optional[str] = None,
    ) -> Optional[str]:
        """
        Publishes a generic real-time event to the specified user's stream.
        """
        if not user_id:
            logger.warning("RealtimeEventDispatcherService: Dropping event %s because no user_id provided.", event)
            return None

        stream_key = stream_user_key(user_id)
        
        try:
            event_id = publish_stream_event(
                stream_key,
                event=event,
                status=status,
                payload=payload,
                job_id=job_id,
                user_id=str(user_id),
                correlation_id=correlation_id,
            )
            return event_id
        except Exception as e:
            logger.error(
                "RealtimeEventDispatcherService: Failed to publish %s to %s: %s",
                event,
                stream_key,
                str(e),
                exc_info=True,
            )
            return None

    @classmethod
    def publish_job_update(
        cls,
        user_id: int | str,
        job_id: str,
        status: str,
        progress: int,
        payload: Optional[Dict[str, Any]] = None,
        event_name: str = "job_update"
    ) -> Optional[str]:
        """
        Helper method to specifically broadcast a job progress update.
        """
        full_payload = {
            "job_id": str(job_id),
            "status": status,
            "progress": progress,
        }
        if payload:
            full_payload.update(payload)
            
        return cls.publish_event(
            user_id=user_id,
            event=event_name,
            payload=full_payload,
            status="info",
            job_id=job_id
        )
