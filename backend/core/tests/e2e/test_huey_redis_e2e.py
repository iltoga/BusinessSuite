import os
import uuid
from pathlib import Path

import pytest
from redis import Redis

try:
    from huey import RedisHuey
except ImportError:
    from huey.contrib.redis_huey import RedisHuey  # type: ignore[import]


def _running_inside_container() -> bool:
    if Path("/.dockerenv").exists():
        return True

    cgroup_path = Path("/proc/1/cgroup")
    if not cgroup_path.exists():
        return False

    cgroup = cgroup_path.read_text(encoding="utf-8", errors="ignore").lower()
    return any(token in cgroup for token in ("docker", "containerd", "kubepods", "podman"))


def _redis_host_for_e2e() -> str:
    return "bs-redis" if _running_inside_container() else "localhost"


def test_huey_task_roundtrip_uses_redis_backend_e2e():
    redis_host = _redis_host_for_e2e()
    redis_port = 6379
    redis_db = int(os.getenv("HUEY_E2E_REDIS_DB", "14"))

    redis_client = Redis(
        host=redis_host,
        port=redis_port,
        db=redis_db,
        socket_connect_timeout=0.5,
        socket_timeout=1,
    )

    try:
        redis_client.ping()
    except Exception as exc:
        pytest.skip(f"Redis is not reachable for Huey E2E on {redis_host}:{redis_port} (db {redis_db}): {exc}")

    huey = RedisHuey(
        name=f"huey-e2e-{uuid.uuid4().hex}",
        immediate=False,
        results=True,
        host=redis_host,
        port=redis_port,
        db=redis_db,
    )

    # The dummy task is defined inside the test so it is active only for this run.
    @huey.task()
    def _dummy_increment(value: int) -> int:
        return value + 1

    result = _dummy_increment(41)
    queued_task = huey.dequeue()

    assert queued_task is not None, "Expected one queued task in Redis, but queue was empty."

    huey.execute(queued_task)
    assert result.get(blocking=True, timeout=5) == 42
