import os


def build_prod_redis_caches() -> dict:
    return {
        "default": {
            "BACKEND": "django_redis.cache.RedisCache",
            "LOCATION": os.getenv("REDIS_URL", "redis://redis:6379/1"),
            "OPTIONS": {"CLIENT_CLASS": "django_redis.client.DefaultClient"},
            "TIMEOUT": 300,
            "KEY_PREFIX": os.getenv("CACHE_KEY_PREFIX", "revisbali"),
        },
        "select2": {
            "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
            "TIMEOUT": 300,
        },
    }
