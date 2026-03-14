import time
from typing import AsyncGenerator

from django.http import StreamingHttpResponse


from api.utils.redis_sse import iter_replay_and_live_events_async
from api.utils.sse_auth import sse_token_auth_required
from core.services.redis_streams import format_sse_event, resolve_last_event_id, stream_user_key

@sse_token_auth_required
def realtime_stream_sse(request):
    """
    Global Multiplexed SSE Stream for a specific User.
    Listens to `user:{user_id}:realtime` Redis Stream and yields generic events 
    from Dramatiq background tasks and other real-time sources.
    """
    user_id = request.user.id
    stream_key = stream_user_key(user_id)
    replay_cursor = resolve_last_event_id(request)

    async def event_stream() -> AsyncGenerator[str, None]:
        # Send initial connection success message for debugging/state sync
        yield format_sse_event(data={"event": "connected", "user_id": user_id})

        async for stream_event in iter_replay_and_live_events_async(
            stream_key=stream_key,
            last_event_id=replay_cursor,
            block_ms=10_000,
        ):
            try:
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
                yield format_sse_event(
                    event=event_name,
                    event_id=stream_event.id,
                    data=payload
                )

            except GeneratorExit:
                return
            except Exception as exc:
                yield format_sse_event(data={"event": "realtime_error", "error": str(exc)})
                return

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response
