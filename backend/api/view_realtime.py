"""
FILE_ROLE: Handles SSE and realtime streaming endpoints for the API app.

KEY_COMPONENTS:
- realtime_stream_sse: Authenticated SSE stream for per-user realtime events.

INTERACTIONS:
- Depends on: api.utils.redis_sse, api.utils.sse_auth, core.services.redis_streams
- Consumed by: frontend realtime listeners and background-task event emitters.

AI_GUIDELINES:
- Keep the stream wrapper focused on connection/auth/formatting concerns.
- Do not add blocking work inside the event loop; stream data should come from Redis helpers and task emitters.
- Preserve SSE formatting and keepalive behavior because clients rely on stable event framing.
"""

import logging
import time
from collections.abc import AsyncGenerator

from api.utils.contracts import get_request_id
from api.utils.redis_sse import iter_replay_and_live_events_async
from api.utils.sse_auth import sse_token_auth_required
from core.services.redis_streams import format_sse_event, resolve_last_event_id, stream_user_key
from django.http import StreamingHttpResponse

logger = logging.getLogger(__name__)

# Server-side max SSE connection duration (seconds).
# Must be shorter than Cloudflare's 100 s proxy timeout.
_SSE_MAX_DURATION_SECONDS = 55


@sse_token_auth_required
async def realtime_stream_sse(request):
    """
    Global Multiplexed SSE Stream for a specific User.
    Listens to `user:{user_id}:realtime` Redis Stream and yields generic events
    from Dramatiq background tasks and other real-time sources.
    """
    user_id = request.user.id
    stream_key = stream_user_key(user_id)
    replay_cursor = resolve_last_event_id(request)
    logger.info(
        "realtime_stream_sse connect user_id=%s request_id=%s replay_cursor=%s",
        user_id,
        get_request_id(request),
        replay_cursor,
    )

    async def event_stream() -> AsyncGenerator[str, None]:
        deadline = time.monotonic() + _SSE_MAX_DURATION_SECONDS

        # Send initial connection success message for debugging/state sync
        yield format_sse_event(data={"event": "connected", "userId": user_id})

        async for stream_event in iter_replay_and_live_events_async(
            stream_key=stream_key,
            last_event_id=replay_cursor,
            block_ms=10_000,
        ):
            try:
                if time.monotonic() >= deadline:
                    return

                if stream_event is None:
                    # Occurs on block timeout; send keepalive
                    yield ": keepalive\n\n"
                    continue

                # Help static type checkers narrow the type
                assert stream_event is not None

                # The payload itself has event formatting built by the dispatcher
                event_name = stream_event.event
                payload = stream_event.payload

                # Wrap it to exact SSE formatting
                yield format_sse_event(event=event_name, event_id=stream_event.id, data=payload)

            except GeneratorExit:
                return
            except Exception as exc:
                logger.exception(
                    "realtime_stream_sse failure user_id=%s request_id=%s error=%s",
                    user_id,
                    get_request_id(request),
                    exc,
                )
                yield format_sse_event(data={"event": "realtime_error", "error": str(exc)})
                return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
