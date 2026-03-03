import os


def build_prod_redis_caches(*, redis_url: str | None = None) -> dict:
    location = redis_url or os.getenv("REDIS_URL", "redis://redis:6379/1")
    return {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": location,
            "OPTIONS": {
                "CLIENT_CLASS": "django_redis.client.DefaultClient",
                "CONNECTION_POOL_KWARGS": {
                    "max_connections": 50,
                    "retry_on_timeout": True,
                },
                "SOCKET_CONNECT_TIMEOUT": 5,
                "SOCKET_TIMEOUT": 5,
            },
            "TIMEOUT": 300,
            "KEY_PREFIX": os.getenv("CACHE_KEY_PREFIX", "revisbali"),
        },
        "select2": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "TIMEOUT": 300,
        },
    }
