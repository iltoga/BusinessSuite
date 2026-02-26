from unittest.mock import patch

from admin_tools import services
from django.test import SimpleTestCase, override_settings


@override_settings(
    CACHES={
        "default": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "LOCATION": "cache-health-service-tests",
        }
    }
)
class CacheHealthServiceTests(SimpleTestCase):
    def test_cache_health_probe_succeeds_with_locmem(self):
        payload = services.get_cache_health_status()

        self.assertTrue(payload["ok"])
        self.assertTrue(payload["userCacheEnabled"])
        self.assertFalse(payload["probeSkipped"])
        self.assertTrue(payload["writeReadDeleteOk"])
        self.assertFalse(payload["redisConfigured"])
        self.assertIsNone(payload["redisConnected"])
        self.assertGreaterEqual(payload["probeLatencyMs"], 0.0)

    @patch("cache.namespace.namespace_manager.is_cache_enabled", return_value=False)
    def test_cache_health_probe_is_skipped_when_user_cache_disabled(self, _is_cache_enabled_mock):
        payload = services.get_cache_health_status(user_id=123)

        self.assertTrue(payload["ok"])
        self.assertFalse(payload["userCacheEnabled"])
        self.assertTrue(payload["probeSkipped"])
        self.assertFalse(payload["writeReadDeleteOk"])
        self.assertIn("disabled", payload["message"].lower())
