"""Tests for Dramatiq scheduler lock and enqueue behavior."""

from types import SimpleNamespace
from unittest.mock import patch

from core.management.commands.run_dramatiq_scheduler import Command, SchedulerLock
from django.test import SimpleTestCase
from django.utils import timezone


class FakeSchedulerRedis:
    def __init__(self):
        self.values = {}
        self.deleted_keys = []
        self.eval_calls = []
        self.set_calls = []

    def set(self, key, value, nx=False, ex=None):
        self.set_calls.append((key, value, nx, ex))
        if nx and key in self.values:
            return False
        self.values[key] = value
        return True

    def eval(self, script, numkeys, key, token, ttl=None):
        self.eval_calls.append((script, numkeys, key, token, ttl))
        if self.values.get(key) != token:
            return 0
        if "expire" in script:
            return 1
        if "del" in script:
            self.deleted_keys.append(key)
            self.values.pop(key, None)
            return 1
        return 0

    def delete(self, key):
        self.deleted_keys.append(key)
        self.values.pop(key, None)
        return 1


class SchedulerCommandTests(SimpleTestCase):
    def test_lock_refresh_and_release_are_token_checked_with_lua(self):
        command = Command()
        redis_client = FakeSchedulerRedis()
        lock = SchedulerLock(key="scheduler:lock", token="owner-token", ttl_seconds=30)

        self.assertTrue(command._acquire_or_refresh_lock(redis_client, lock))
        self.assertEqual(redis_client.values[lock.key], lock.token)

        self.assertTrue(command._acquire_or_refresh_lock(redis_client, lock))
        self.assertEqual(redis_client.eval_calls[-1][2:], (lock.key, lock.token, lock.ttl_seconds))

        redis_client.values[lock.key] = "other-token"
        self.assertFalse(command._acquire_or_refresh_lock(redis_client, lock))

        command._release_lock(redis_client, lock)
        self.assertEqual(redis_client.values[lock.key], "other-token")

        redis_client.values[lock.key] = lock.token
        command._release_lock(redis_client, lock)
        self.assertNotIn(lock.key, redis_client.values)

    def test_run_due_tasks_clears_dedupe_key_on_enqueue_failure_and_continues(self):
        command = Command()
        redis_client = FakeSchedulerRedis()
        now = timezone.now().replace(second=0, microsecond=0)
        delayed = []

        failing_task = SimpleNamespace(delay=lambda: (_ for _ in ()).throw(RuntimeError("broker down")))
        successful_task = SimpleNamespace(delay=lambda: delayed.append("ok"))
        entries = (
            SimpleNamespace(name="failing.task", schedule=SimpleNamespace(is_due=lambda _now: True), task=failing_task),
            SimpleNamespace(name="successful.task", schedule=SimpleNamespace(is_due=lambda _now: True), task=successful_task),
        )

        with patch("core.management.commands.run_dramatiq_scheduler.iter_periodic_tasks", return_value=entries):
            command._run_due_tasks(redis_client, now=now)

        failing_key = f"dramatiq:scheduler:dedupe:failing.task:{now.isoformat()}"
        successful_key = f"dramatiq:scheduler:dedupe:successful.task:{now.isoformat()}"

        self.assertIn(failing_key, redis_client.deleted_keys)
        self.assertEqual(redis_client.values.get(successful_key), "1")
        self.assertEqual(delayed, ["ok"])

    def test_write_heartbeat_sets_epoch_with_ttl(self):
        command = Command()
        redis_client = FakeSchedulerRedis()

        with patch("core.management.commands.run_dramatiq_scheduler.time.time", return_value=1234.5):
            command._write_heartbeat(redis_client, heartbeat_key="scheduler:heartbeat", ttl_seconds=90)

        self.assertEqual(redis_client.set_calls[-1], ("scheduler:heartbeat", "1234.5", False, 90))
