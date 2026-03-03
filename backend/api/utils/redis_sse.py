from __future__ import annotations

from collections.abc import Generator

from core.services.redis_streams import StreamEvent, read_stream_blocking, read_stream_replay



def iter_replay_and_live_events(
    *,
    stream_key: str,
    last_event_id: str | None,
    block_ms: int = 15_000,
    replay_count: int = 500,
) -> Generator[StreamEvent | None, None, None]:
    cursor = last_event_id

    if last_event_id:
        replay_events = read_stream_replay(stream_key, last_event_id=last_event_id, count=replay_count)
        for event in replay_events:
            cursor = event.id
            yield event

    while True:
        events = read_stream_blocking(stream_key, last_event_id=cursor, block_ms=block_ms, count=200)
        if not events:
            yield None
            continue

        for event in events:
            cursor = event.id
            yield event
