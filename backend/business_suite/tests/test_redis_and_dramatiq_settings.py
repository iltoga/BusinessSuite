import hashlib
import importlib
import os
import subprocess
import sys
from unittest.mock import patch

from business_suite.settings.base import _default_dramatiq_workers
from business_suite.settings.cache_backends import build_prod_redis_caches
from core.tasks.runtime import QUEUE_DEFAULT, QUEUE_DOC_CONVERSION, QUEUE_LOW, QUEUE_REALTIME, QUEUE_SCHEDULED
from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.test import SimpleTestCase, override_settings
from invoices.tasks.document_jobs import run_invoice_document_job
from invoices.tasks.download_jobs import run_invoice_download_job


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
    def _load_base_settings_snapshot(
        self,
        *,
        env_updates: dict[str, str | None],
        fields: list[str],
    ) -> dict[str, object]:
        from business_suite.settings import base as base_settings

        originals = {key: os.environ.get(key) for key in env_updates}
        try:
            for key, value in env_updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            reloaded = importlib.reload(base_settings)
            return {field: getattr(reloaded, field) for field in fields}
        finally:
            for key, value in originals.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
            importlib.reload(base_settings)

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

    def test_invoice_document_jobs_default_to_doc_conversion_queue(self):
        self.assertEqual(getattr(settings, "DRAMATIQ_INVOICE_DOC_QUEUE", ""), QUEUE_DOC_CONVERSION)
        self.assertEqual(run_invoice_document_job.actor.queue_name, QUEUE_DOC_CONVERSION)
        self.assertEqual(run_invoice_download_job.actor.queue_name, QUEUE_DOC_CONVERSION)

    def test_document_validator_model_remains_blank_when_unset(self):
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "LLM_PROVIDER": "openrouter",
                "LLM_DEFAULT_MODEL": "test/vision-model",
                "DOCUMENT_VALIDATOR_MODEL": None,
            },
            fields=["DOCUMENT_VALIDATOR_MODEL"],
        )
        self.assertEqual(snapshot["DOCUMENT_VALIDATOR_MODEL"], "")

    def test_llm_default_model_stays_on_env_value_when_provider_is_groq(self):
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "LLM_PROVIDER": "groq",
                "LLM_DEFAULT_MODEL": "google/gemini-3-flash-preview",
                "GROQ_DEFAULT_MODEL": "meta-llama/custom-groq-model",
            },
            fields=["LLM_DEFAULT_MODEL"],
        )
        self.assertEqual(snapshot["LLM_DEFAULT_MODEL"], "google/gemini-3-flash-preview")

    def test_llm_default_model_falls_back_to_required_default_when_env_model_missing(self):
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "LLM_PROVIDER": "groq",
                "LLM_DEFAULT_MODEL": "",
                "GROQ_DEFAULT_MODEL": "",
            },
            fields=["LLM_DEFAULT_MODEL"],
        )
        self.assertEqual(snapshot["LLM_DEFAULT_MODEL"], "google/gemini-3-flash-preview")

    def test_workflow_model_overrides_preserve_explicit_values_across_provider_switches(self):
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "LLM_PROVIDER": "groq",
                "GROQ_DEFAULT_MODEL": "meta-llama/custom-groq-model",
                "DOCUMENT_CATEGORIZER_MODEL": "openrouter/specific-model",
                "DOCUMENT_CATEGORIZER_MODEL_HIGH": "openrouter/high-model",
                "DOCUMENT_VALIDATOR_MODEL": "openrouter/validator-model",
                "CHECK_PASSPORT_MODEL": "openrouter/passport-model",
            },
            fields=[
                "LLM_DEFAULT_MODEL",
                "DOCUMENT_CATEGORIZER_MODEL",
                "DOCUMENT_CATEGORIZER_MODEL_HIGH",
                "DOCUMENT_VALIDATOR_MODEL",
                "CHECK_PASSPORT_MODEL",
            ],
        )
        self.assertEqual(snapshot["DOCUMENT_CATEGORIZER_MODEL"], "openrouter/specific-model")
        self.assertEqual(snapshot["DOCUMENT_CATEGORIZER_MODEL_HIGH"], "openrouter/high-model")
        self.assertEqual(snapshot["DOCUMENT_VALIDATOR_MODEL"], "openrouter/validator-model")
        self.assertEqual(snapshot["CHECK_PASSPORT_MODEL"], "openrouter/passport-model")

    def test_workflow_model_overrides_remain_blank_when_unset(self):
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "LLM_PROVIDER": "openrouter",
                "LLM_DEFAULT_MODEL": "google/gemini-2.5-flash-lite",
                "DOCUMENT_CATEGORIZER_MODEL": None,
                "DOCUMENT_CATEGORIZER_MODEL_HIGH": None,
                "DOCUMENT_VALIDATOR_MODEL": None,
                "CHECK_PASSPORT_MODEL": None,
            },
            fields=[
                "DOCUMENT_CATEGORIZER_MODEL",
                "DOCUMENT_CATEGORIZER_MODEL_HIGH",
                "DOCUMENT_VALIDATOR_MODEL",
                "CHECK_PASSPORT_MODEL",
            ],
        )
        self.assertEqual(snapshot["DOCUMENT_CATEGORIZER_MODEL"], "")
        self.assertEqual(snapshot["DOCUMENT_CATEGORIZER_MODEL_HIGH"], "")
        self.assertEqual(snapshot["DOCUMENT_VALIDATOR_MODEL"], "")
        self.assertEqual(snapshot["CHECK_PASSPORT_MODEL"], "")

    def test_jwt_signing_key_uses_secret_key_when_long_enough(self):
        long_secret = "a-very-long-secret-key-for-jwt-signing-1234567890"
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "DJANGO_SETTINGS_MODULE": "business_suite.settings.dev",
                "SECRET_KEY": long_secret,
                "JWT_SIGNING_KEY": None,
            },
            fields=["JWT_SIGNING_KEY"],
        )
        self.assertEqual(snapshot["JWT_SIGNING_KEY"], long_secret)

    def test_jwt_signing_key_derives_sha256_when_short_in_non_prod_settings(self):
        short_secret = "short-secret-key-24-bytes"
        snapshot = self._load_base_settings_snapshot(
            env_updates={
                "DJANGO_SETTINGS_MODULE": "business_suite.settings.dev",
                "SECRET_KEY": short_secret,
                "JWT_SIGNING_KEY": None,
            },
            fields=["JWT_SIGNING_KEY"],
        )
        self.assertEqual(snapshot["JWT_SIGNING_KEY"], hashlib.sha256(short_secret.encode("utf-8")).hexdigest())

    def test_short_jwt_signing_key_raises_in_prod_settings(self):
        from business_suite.settings import base as base_settings

        env_updates = {
            "DJANGO_SETTINGS_MODULE": "business_suite.settings.prod",
            "SECRET_KEY": "short-secret-key-24-bytes",
            "JWT_SIGNING_KEY": None,
        }
        originals = {key: os.environ.get(key) for key in env_updates}

        try:
            for key, value in env_updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

            with self.assertRaises(ImproperlyConfigured):
                importlib.reload(base_settings)
        finally:
            for key, value in originals.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
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

    def test_worker_style_import_registers_calendar_sync_actors(self):
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env = os.environ.copy()
        env.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
        env.setdefault("MEDIA_ROOT", "./media")
        env.setdefault("SECRET_KEY", "django-insecure-dev-only")

        code = (
            "import business_suite.dramatiq as runtime; "
            "names=sorted(name for name in runtime.broker.actors.keys() if 'calendar' in name); "
            "print('ACTORS_START'); "
            "[print(name) for name in names]; "
            "print('ACTORS_END')"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        output = result.stdout
        self.assertIn("core.tasks.calendar_sync.create_google_event_task", output)
        self.assertIn("core.tasks.calendar_sync.update_google_event_task", output)
        self.assertIn("core.tasks.calendar_sync.delete_google_event_task", output)

    def test_worker_style_import_binds_signal_task_lookup_to_runtime_broker(self):
        backend_dir = os.path.abspath(os.path.join(os.path.dirname(__file__), "..", ".."))
        env = os.environ.copy()
        env.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
        env.setdefault("MEDIA_ROOT", "./media")
        env.setdefault("SECRET_KEY", "django-insecure-dev-only")

        code = (
            "import business_suite.dramatiq as runtime; "
            "import core.signals_calendar as sc; "
            "print(sc._send_calendar_task.__name__); "
            "print(runtime.broker.get_actor(sc.CREATE_GOOGLE_EVENT_TASK_NAME).actor_name); "
            "print(runtime.broker.get_actor(sc.UPDATE_GOOGLE_EVENT_TASK_NAME).actor_name); "
            "print(runtime.broker.get_actor(sc.DELETE_GOOGLE_EVENT_TASK_NAME).actor_name)"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=backend_dir,
            env=env,
            capture_output=True,
            text=True,
            check=True,
        )

        output = result.stdout
        self.assertIn("_send_calendar_task", output)
        self.assertIn("core.tasks.calendar_sync.create_google_event_task", output)
        self.assertIn("core.tasks.calendar_sync.update_google_event_task", output)
        self.assertIn("core.tasks.calendar_sync.delete_google_event_task", output)

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
