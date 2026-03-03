import os
from unittest.mock import patch

from django.test import SimpleTestCase, override_settings

from core.services.redis_client import build_redis_url


class RedisClientUrlResolutionTests(SimpleTestCase):
    @override_settings(DRAMATIQ_REDIS_DB=0, DRAMATIQ_REDIS_URL="")
    def test_build_redis_url_prefers_redis_url_over_host_port(self):
        with patch.dict(
            os.environ,
            {
                "REDIS_URL": "rediss://user:pass@secure-redis.example.com:6380/5?ssl_cert_reqs=required",
                "REDIS_HOST": "localhost",
                "REDIS_PORT": "6379",
            },
            clear=False,
        ):
            resolved = build_redis_url()

        self.assertEqual(
            resolved,
            "rediss://user:pass@secure-redis.example.com:6380/0?ssl_cert_reqs=required",
        )

    @override_settings(DRAMATIQ_REDIS_DB=3, DRAMATIQ_REDIS_URL="redis://dramatiq-user:dramatiq-pass@broker.local:6379/9")
    def test_build_redis_url_prefers_explicit_dramatiq_redis_url(self):
        with patch.dict(
            os.environ,
            {
                "REDIS_URL": "redis://fallback:6379/1",
                "REDIS_HOST": "localhost",
                "REDIS_PORT": "6379",
            },
            clear=False,
        ):
            resolved = build_redis_url()

        self.assertEqual(resolved, "redis://dramatiq-user:dramatiq-pass@broker.local:6379/3")
