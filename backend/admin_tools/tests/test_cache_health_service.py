from django.test import SimpleTestCase, override_settings

from admin_tools import services


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
        self.assertTrue(payload["writeReadDeleteOk"])
        self.assertFalse(payload["redisConfigured"])
        self.assertIsNone(payload["redisConnected"])
        self.assertGreaterEqual(payload["probeLatencyMs"], 0.0)
