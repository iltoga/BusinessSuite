from __future__ import annotations

import json
from typing import Any, Mapping


class QueuePayloadError(ValueError):
    """Raised when a queue payload cannot be decoded."""


def encode_payload(payload: Mapping[str, Any] | None) -> bytes | None:
    if payload is None:
        return None
    return json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8")


def decode_payload(payload: bytes | bytearray | memoryview | None) -> dict[str, Any]:
    if payload is None:
        return {}

    if isinstance(payload, memoryview):
        raw = payload.tobytes()
    elif isinstance(payload, bytearray):
        raw = bytes(payload)
    else:
        raw = payload

    if not raw:
        return {}

    try:
        data = json.loads(raw.decode("utf-8"))
    except Exception as exc:
        raise QueuePayloadError("Invalid queue payload.") from exc

    if data is None:
        return {}
    if not isinstance(data, dict):
        raise QueuePayloadError("Queue payload must be a JSON object.")
    return data
