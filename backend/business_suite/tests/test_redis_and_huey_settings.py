import os
from unittest.mock import patch

from django.conf import settings
from django.test import SimpleTestCase, override_settings

from business_suite.settings.base import _build_huey_settings
from business_suite.settings.cache_backends import build_prod_redis_caches


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


class HueySettingsTests(SimpleTestCase):
    def test_huey_uses_redis_in_non_test_mode(self):
        with patch.dict(
            os.environ,
            {"REDIS_HOST": "bs-redis", "REDIS_PORT": "6379", "HUEY_REDIS_DB": "5"},
            clear=False,
        ):
            huey_settings = _build_huey_settings(testing=False)

        self.assertIn(
            huey_settings["huey_class"],
            {"huey.contrib.redis_huey.RedisHuey", "huey.RedisHuey"},
        )
        self.assertEqual(huey_settings["connection"]["host"], "bs-redis")
        self.assertEqual(huey_settings["connection"]["port"], 6379)
        self.assertEqual(huey_settings["connection"]["db"], 5)

    def test_huey_defaults_to_localhost_when_running_on_host(self):
        with (
            patch.dict(os.environ, {"REDIS_PORT": "6379", "HUEY_REDIS_DB": "0"}, clear=True),
            patch("business_suite.settings.base.os.path.exists", return_value=False),
        ):
            huey_settings = _build_huey_settings(testing=False)

        self.assertEqual(huey_settings["connection"]["host"], "localhost")

    def test_huey_defaults_to_bs_redis_when_running_in_container(self):
        with (
            patch.dict(os.environ, {"REDIS_PORT": "6379", "HUEY_REDIS_DB": "0"}, clear=True),
            patch("business_suite.settings.base.os.path.exists", return_value=True),
        ):
            huey_settings = _build_huey_settings(testing=False)

        self.assertEqual(huey_settings["connection"]["host"], "bs-redis")

    def test_huey_uses_sqlite_when_testing(self):
        huey_settings = _build_huey_settings(testing=True)

        self.assertEqual(huey_settings["huey_class"], "huey.contrib.sql_huey.SqlHuey")
        self.assertTrue(huey_settings["results"])
