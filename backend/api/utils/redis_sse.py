"""Redis-backed SSE helper utilities for event streaming endpoints."""

from __future__ import annotations

import logging
import time
from collections.abc import Generator

from core.services.redis_streams import StreamEvent, read_stream_blocking, read_stream_replay

logger = logging.getLogger(__name__)


def iter_replay_and_live_events(
    *,
    stream_key: str,
    last_event_id: str | None,
    block_ms: int = 15_000,
    replay_count: int = 500,
) -> Generator[StreamEvent | None, None, None]:
    cursor = last_event_id

    if last_event_id:
        logger.info("SSE replay requested for stream '%s' from last_event_id=%s", stream_key, last_event_id)
        try:
            replay_events = read_stream_replay(stream_key, last_event_id=last_event_id, count=replay_count)
        except Exception as exc:
            logger.warning("SSE replay read failed for stream '%s': %s", stream_key, exc)
        else:
            for event in replay_events:
                cursor = event.id
                yield event

    while True:
        try:
            events = read_stream_blocking(stream_key, last_event_id=cursor, block_ms=block_ms, count=200)
        except Exception as exc:
            logger.warning("SSE live read failed for stream '%s': %s", stream_key, exc)
            # Avoid tight-looping when Redis is unavailable.
            time.sleep(min(max(block_ms, 250), 1000) / 1000.0)
            yield None
            continue
        if not events:
            yield None
            continue

        for event in events:
            cursor = event.id
            yield event


import asyncio
from collections.abc import AsyncGenerator


async def iter_replay_and_live_events_async(
    *,
    stream_key: str,
    last_event_id: str | None,
    block_ms: int = 15_000,
    replay_count: int = 500,
) -> AsyncGenerator[StreamEvent | None, None]:
    cursor = last_event_id

    if last_event_id:
        logger.info("SSE replay requested for stream '%s' from last_event_id=%s", stream_key, last_event_id)
        try:
            replay_events = read_stream_replay(stream_key, last_event_id=last_event_id, count=replay_count)
        except Exception as exc:
            logger.warning("SSE replay read failed for stream '%s': %s", stream_key, exc)
        else:
            for event in replay_events:
                cursor = event.id
                yield event

    from core.services.redis_streams import read_stream_blocking_async

    while True:
        try:
            events = await read_stream_blocking_async(stream_key, last_event_id=cursor, block_ms=block_ms, count=200)
        except asyncio.CancelledError:
            break
        except Exception as exc:
            logger.warning("SSE live async read failed for stream '%s': %s", stream_key, exc)
            # Avoid tight-looping when Redis is unavailable.
            await asyncio.sleep(min(max(block_ms, 250), 1000) / 1000.0)
            yield None
            continue

        if not events:
            yield None
            continue

        for event in events:
            cursor = event.id
            yield event
