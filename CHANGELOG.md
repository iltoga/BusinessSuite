# Changelog

## 2026-02-17

- Replaced memcached with Redis across runtime configuration.
- Switched production Django cache backend to `django-redis` (`RedisCache`).
- Switched non-test Huey broker from `SqlHuey` to `RedisHuey` (test mode remains Sqlite/SqlHuey).
- Updated Docker Compose (`docker-compose.yml`, `docker-compose-local.yml`) to add `redis` service and remove `memcached`.
- Standardized Redis container name to `bs-redis` in local and production compose files.
- Updated local compose workflow to infra-only containers (`db`, `bs-redis`, `bs-alloy`, `bs-loki`, `bs-grafana`) with backend/worker/frontend running on host.
- Updated deployment workflow container cleanup from `memcached` to `bs-redis`.
- Updated `.env.example` with Redis/Huey env variables and removed `MEMCACHED_HOST`.
- Updated Python dependencies to remove `pymemcache` and add `django-redis` + `redis`.
- Added tests for Redis cache/Huey settings and extended invoice sequence cache-increment coverage.
- Added rollout/rollback guide: `howtos/REDIS_MIGRATION.md`.
