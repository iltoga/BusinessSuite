from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

from django.conf import settings

from core.services.redis_client import get_redis_client

STREAM_KEY_USER_PREFIX = "stream:user"
STREAM_KEY_FILE_PREFIX = "stream:file"
STREAM_KEY_JOB_PREFIX = "stream:job"


@dataclass(frozen=True)
class StreamEvent:
    id: str
    event: str
    status: str
    timestamp: str
    payload: dict[str, Any]
    raw: dict[str, str]



def _stream_maxlen() -> int:
    return int(getattr(settings, "STREAM_MAXLEN", 10_000) or 10_000)



def _stream_ttl_seconds() -> int:
    return int(getattr(settings, "STREAM_TTL_SECONDS", 7 * 24 * 60 * 60) or (7 * 24 * 60 * 60))



def stream_user_key(user_id: int | str) -> str:
    return f"{STREAM_KEY_USER_PREFIX}:{user_id}"



def stream_file_key(file_id: int | str) -> str:
    return f"{STREAM_KEY_FILE_PREFIX}:{file_id}"



def stream_job_key(job_id: int | str) -> str:
    return f"{STREAM_KEY_JOB_PREFIX}:{job_id}"



def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()



def _decode_dict(raw: dict[Any, Any]) -> dict[str, str]:
    decoded: dict[str, str] = {}
    for key, value in raw.items():
        k = key.decode("utf-8") if isinstance(key, (bytes, bytearray)) else str(key)
        if isinstance(value, (bytes, bytearray)):
            decoded[k] = value.decode("utf-8")
        else:
            decoded[k] = str(value)
    return decoded



def _decode_stream_id(raw_id: Any) -> str:
    return raw_id.decode("utf-8") if isinstance(raw_id, (bytes, bytearray)) else str(raw_id)



def _to_stream_event(stream_id: Any, raw_fields: dict[Any, Any]) -> StreamEvent:
    fields = _decode_dict(raw_fields)
    payload_raw = fields.get("payload", "{}")
    try:
        payload = json.loads(payload_raw) if payload_raw else {}
    except json.JSONDecodeError:
        payload = {"raw": payload_raw}

    return StreamEvent(
        id=_decode_stream_id(stream_id),
        event=fields.get("event", "message"),
        status=fields.get("status", "info"),
        timestamp=fields.get("timestamp", _utc_now_iso()),
        payload=payload if isinstance(payload, dict) else {"value": payload},
        raw=fields,
    )



def publish_stream_event(
    stream_key: str,
    *,
    event: str,
    status: str = "info",
    payload: dict[str, Any] | None = None,
    job_id: str | None = None,
    user_id: str | None = None,
    file_id: str | None = None,
    correlation_id: str | None = None,
) -> str:
    client = get_redis_client()
    fields: dict[str, str] = {
        "event": event,
        "status": status,
        "timestamp": _utc_now_iso(),
        "payload": json.dumps(payload or {}, separators=(",", ":")),
    }
    if job_id:
        fields["job_id"] = str(job_id)
    if user_id:
        fields["user_id"] = str(user_id)
    if file_id:
        fields["file_id"] = str(file_id)
    if correlation_id:
        fields["correlation_id"] = str(correlation_id)

    stream_id = client.xadd(stream_key, fields, maxlen=_stream_maxlen(), approximate=True)

    ttl_seconds = _stream_ttl_seconds()
    if ttl_seconds > 0:
        client.expire(stream_key, ttl_seconds)

    return _decode_stream_id(stream_id)



def read_stream_replay(
    stream_key: str,
    *,
    last_event_id: str | None,
    count: int = 200,
) -> list[StreamEvent]:
    client = get_redis_client()
    min_id = f"({last_event_id}" if last_event_id else "-"
    entries = client.xrange(stream_key, min=min_id, max="+", count=count)
    return [_to_stream_event(stream_id, raw_fields) for stream_id, raw_fields in entries]



def read_stream_blocking(
    stream_key: str,
    *,
    last_event_id: str | None,
    block_ms: int = 15_000,
    count: int = 200,
) -> list[StreamEvent]:
    # XREAD with BLOCK can legitimately wait up to block_ms before Redis replies.
    # Keep client socket timeout longer than that window to avoid false timeouts.
    socket_timeout = max(5.0, (block_ms / 1000.0) + 5.0)
    client = get_redis_client(socket_timeout=socket_timeout)
    cursor = last_event_id or "$"
    result = client.xread(streams={stream_key: cursor}, block=block_ms, count=count)
    if not result:
        return []

    events: list[StreamEvent] = []
    for _, entries in result:
        for stream_id, raw_fields in entries:
            events.append(_to_stream_event(stream_id, raw_fields))
    return events


async def read_stream_blocking_async(
    stream_key: str,
    *,
    last_event_id: str | None,
    block_ms: int = 15_000,
    count: int = 200,
) -> list[StreamEvent]:
    from core.services.redis_client import get_async_redis_client
    socket_timeout = max(5.0, (block_ms / 1000.0) + 5.0)
    client = get_async_redis_client(socket_timeout=socket_timeout)
    cursor = last_event_id or "$"
    result = await client.xread(streams={stream_key: cursor}, block=block_ms, count=count)
    if not result:
        return []

    events: list[StreamEvent] = []
    for _, entries in result:
        for stream_id, raw_fields in entries:
            events.append(_to_stream_event(stream_id, raw_fields))
    return events



def resolve_last_event_id(request) -> str | None:
    last_event_id = request.headers.get("Last-Event-ID") or request.GET.get("last_event_id")
    if not last_event_id:
        return None
    return str(last_event_id).strip() or None



def format_sse_event(*, data: dict[str, Any], event: str | None = None, event_id: str | None = None) -> str:
    lines: list[str] = []
    if event_id:
        lines.append(f"id: {event_id}")
    if event:
        lines.append(f"event: {event}")
    lines.append(f"data: {json.dumps(data)}")
    return "\n".join(lines) + "\n\n"
