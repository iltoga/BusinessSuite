import os
import importlib
from unittest.mock import patch

from business_suite.settings.base import _default_dramatiq_workers
from business_suite.settings.cache_backends import build_prod_redis_caches
from core.tasks.runtime import QUEUE_DEFAULT, QUEUE_DOC_CONVERSION, QUEUE_LOW, QUEUE_REALTIME, QUEUE_SCHEDULED
from django.conf import settings
from django.test import SimpleTestCase, override_settings


class RedisCacheSettingsTests(SimpleTestCase):
    def test_prod_cache_uses_django_redis_when_redis_url_present(self):
        with patch.dict(
            os.environ,
            {"REDIS_URL": "redis://redis:6379/9", "CACHE_KEY_PREFIX": "rspec"},
            clear=False,
        ):
            caches = build_prod_redis_caches()

        self.assertEqual(caches["default"]["BACKEND"], "django_redis.cache.RedisCache")
        self.assertEqual(caches["default"]["LOCATION"], "redis://redis:6379/9")
        self.assertEqual(caches["default"]["KEY_PREFIX"], "rspec")
        self.assertEqual(caches["default"]["OPTIONS"]["CLIENT_CLASS"], "django_redis.client.DefaultClient")

        with override_settings(CACHES=caches):
            self.assertEqual(settings.CACHES["default"]["BACKEND"], "django_redis.cache.RedisCache")


class DramatiqSettingsTests(SimpleTestCase):
    def test_dramatiq_worker_default_is_four_for_task_worker_component(self):
        with patch.dict(os.environ, {"COMPONENT": "task_worker"}, clear=False):
            self.assertEqual(_default_dramatiq_workers(), "4")

    def test_dramatiq_worker_default_is_four_for_dramatiq_command(self):
        with (
            patch.dict(os.environ, {"COMPONENT": ""}, clear=False),
            patch("business_suite.settings.base.sys.argv", ["dramatiq", "business_suite.dramatiq"]),
        ):
            self.assertEqual(_default_dramatiq_workers(), "4")

    def test_dramatiq_worker_default_is_two_for_backend(self):
        with (
            patch.dict(os.environ, {"COMPONENT": ""}, clear=False),
            patch("business_suite.settings.base.sys.argv", ["manage.py", "runserver"]),
        ):
            self.assertEqual(_default_dramatiq_workers(), "2")

    def test_stream_settings_have_defaults(self):
        self.assertGreaterEqual(int(getattr(settings, "STREAM_MAXLEN", 0)), 1)
        self.assertGreaterEqual(int(getattr(settings, "STREAM_TTL_SECONDS", 0)), 1)

    def test_default_namespace_yields_expected_redis_queue_keys(self):
        self.assertEqual(getattr(settings, "DRAMATIQ_NAMESPACE", ""), "dramatiq:queue")

    def test_results_settings_have_defaults(self):
        self.assertTrue(getattr(settings, "DRAMATIQ_RESULTS_ENABLED", False))
        self.assertTrue(getattr(settings, "DRAMATIQ_RESULTS_STORE_RESULTS", False))
        self.assertGreaterEqual(int(getattr(settings, "DRAMATIQ_RESULTS_TTL_MS", 0)), 1)
        self.assertEqual(getattr(settings, "DRAMATIQ_RESULTS_NAMESPACE", ""), "dramatiq:results")

    def test_priority_queue_names_are_dramatiq_compatible(self):
        self.assertEqual(QUEUE_REALTIME, "realtime")
        self.assertEqual(QUEUE_DEFAULT, "default")
        self.assertEqual(QUEUE_SCHEDULED, "scheduled")
        self.assertEqual(QUEUE_LOW, "low")
        self.assertEqual(QUEUE_DOC_CONVERSION, "doc_conversion")

    def test_document_validator_model_defaults_to_llm_default_when_unset(self):
        from business_suite.settings import base as base_settings

        original_llm_default_model = os.environ.get("LLM_DEFAULT_MODEL")
        original_document_validator_model = os.environ.get("DOCUMENT_VALIDATOR_MODEL")
        try:
            os.environ["LLM_DEFAULT_MODEL"] = "test/vision-model"
            os.environ.pop("DOCUMENT_VALIDATOR_MODEL", None)
            reloaded = importlib.reload(base_settings)
            self.assertEqual(reloaded.DOCUMENT_VALIDATOR_MODEL, "test/vision-model")
        finally:
            if original_llm_default_model is None:
                os.environ.pop("LLM_DEFAULT_MODEL", None)
            else:
                os.environ["LLM_DEFAULT_MODEL"] = original_llm_default_model

            if original_document_validator_model is None:
                os.environ.pop("DOCUMENT_VALIDATOR_MODEL", None)
            else:
                os.environ["DOCUMENT_VALIDATOR_MODEL"] = original_document_validator_model

            importlib.reload(base_settings)

    def test_core_periodic_actors_are_registered_on_broker(self):
        from business_suite import dramatiq as dramatiq_runtime

        actor_names = set(dramatiq_runtime.broker.actors.keys())
        expected = {
            "core.dispatch_due_calendar_reminders",
            "core.sync_push_periodic",
            "core.sync_pull_periodic",
        }
        missing = expected - actor_names
        self.assertFalse(missing, f"Missing Dramatiq actors: {sorted(missing)}")

    def test_results_middleware_is_registered_on_broker(self):
        from business_suite import dramatiq as dramatiq_runtime

        results_middleware = next(
            (middleware for middleware in dramatiq_runtime.broker.middleware if type(middleware).__name__ == "Results"),
            None,
        )
        self.assertIsNotNone(results_middleware)
        self.assertTrue(bool(getattr(results_middleware, "store_results", False)))
        self.assertEqual(
            int(getattr(results_middleware, "result_ttl", 0)),
            int(getattr(settings, "DRAMATIQ_RESULTS_TTL_MS", 0)),
        )
