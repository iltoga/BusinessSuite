"""End-to-end tests for Dramatiq and Redis integration."""

import os
import uuid
from pathlib import Path

import dramatiq
import pytest
from dramatiq.brokers.redis import RedisBroker
from redis import Redis


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


def test_dramatiq_queue_roundtrip_uses_redis_backend_e2e():
    redis_host = _redis_host_for_e2e()
    redis_port = 6379
    redis_db = int(os.getenv("DRAMATIQ_E2E_REDIS_DB", "14"))

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
        pytest.skip(f"Redis is not reachable for Dramatiq E2E on {redis_host}:{redis_port} (db {redis_db}): {exc}")

    namespace = f"dramatiq-e2e-{uuid.uuid4().hex}"
    broker = RedisBroker(
        url=f"redis://{redis_host}:{redis_port}/{redis_db}",
        namespace=namespace,
    )
    broker.flush("default")

    @dramatiq.actor(
        broker=broker,
        queue_name="default",
        actor_name=f"{namespace}.dummy_increment",
    )
    def _dummy_increment(value: int) -> int:
        return value + 1

    message = _dummy_increment.message(41)
    broker.enqueue(message)

    consumer = broker.consume("default", timeout=250)
    received = None
    try:
        for _ in range(20):
            candidate = next(consumer)
            if candidate is None:
                continue
            received = candidate
            break
    finally:
        if received is not None:
            consumer.ack(received)
        consumer.close()
        broker.flush("default")

    assert received is not None, "Expected one queued message in Redis, but queue was empty."
    assert received.actor_name == _dummy_increment.actor_name
    assert received.args == (41,)
