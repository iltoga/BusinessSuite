import os
from unittest.mock import patch

from business_suite.settings import base as base_settings
from business_suite.settings.cache_backends import build_prod_redis_caches
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


class PgQueuerSettingsTests(SimpleTestCase):
    def test_pgqueue_defaults_are_loaded(self):
        self.assertEqual(base_settings.PGQUEUE_CHANNEL, os.getenv("PGQUEUE_CHANNEL", "ch_pgqueuer"))
        self.assertEqual(base_settings.PGQUEUE_BATCH_SIZE, int(os.getenv("PGQUEUE_BATCH_SIZE", "10")))
        self.assertEqual(
            base_settings.PGQUEUE_DEQUEUE_TIMEOUT_SECONDS,
            float(os.getenv("PGQUEUE_DEQUEUE_TIMEOUT_SECONDS", "30")),
        )

    def test_redis_host_defaults_to_localhost_when_running_on_host(self):
        with (
            patch.dict(os.environ, {"REDIS_PORT": "6379"}, clear=True),
            patch("business_suite.settings.base.os.path.exists", return_value=False),
        ):
            self.assertEqual(base_settings._resolved_redis_host(), "localhost")

    def test_redis_host_defaults_to_bs_redis_when_running_in_container(self):
        with (
            patch.dict(os.environ, {"REDIS_PORT": "6379"}, clear=True),
            patch("business_suite.settings.base.os.path.exists", return_value=True),
        ):
            self.assertEqual(base_settings._resolved_redis_host(), "bs-redis")
