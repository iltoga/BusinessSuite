# Redis Migration (Cache + PgQueuer Broker)

This document describes the memcached -> Redis cutover for RevisBaliCRM.

## Scope

- Django production cache backend: `PyMemcacheCache` -> `django_redis.cache.RedisCache`
- PgQueuer broker in non-test environments: SQL-backed PgQueuer -> Redis-backed PgQueuer
- Compose services: remove `memcached`, add `redis`
- Redis container naming: `bs-redis` (service name remains `redis`)

## Environment Variables

Set these values in `.env`:

- `REDIS_URL=redis://localhost:6379/1` for host-run local dev, or `redis://bs-redis:6379/1` for containerized app services
- `REDIS_HOST=localhost` for host-run local dev, or `bs-redis` for containerized app services
- `REDIS_PORT=6379`
- `PGQUEUE_CHANNEL=0`
- `CACHE_KEY_PREFIX=revisbali`

## Local Development (docker-compose-local.yml)

In local development, only infrastructure runs in containers. Backend, PgQueuer worker, and frontend run on host.

1. Start infra:
   - `docker compose -f docker-compose-local.yml up -d db redis bs-loki bs-grafana bs-alloy`
2. Run app processes on host:
   - backend: `cd backend && DJANGO_SETTINGS_MODULE=business_suite.settings ../.venv/bin/python manage.py runserver`
   - worker: `cd backend && DJANGO_SETTINGS_MODULE=business_suite.settings ../.venv/bin/pgq run business_suite.pgqueue:factory`
   - frontend: run your local frontend command (host Node/NVM)
3. Local smoke checks:
   - `docker compose -f docker-compose-local.yml ps`
   - `cd backend && DJANGO_SETTINGS_MODULE=business_suite.settings ../.venv/bin/python manage.py shell -c "from django.core.cache import cache; cache.set('redis_smoke', 1, 60); cache.incr('redis_smoke'); print(cache.get('redis_smoke'))"`

## Production Rollout (docker-compose.yml)

1. Prepare deploy:
   - Deploy code/config changes and new dependencies (`django-redis`, `redis`).
2. Stop worker before cutover:
   - `docker compose stop bs-worker`
3. Start/update Redis + app services:
   - `docker compose up -d --remove-orphans redis bs-core bs-frontend`
4. Start worker on Redis broker:
   - `docker compose up -d bs-worker`
5. Verify:
   - `docker compose ps`
   - `docker compose logs -f bs-worker`
   - `docker compose exec bs-core python manage.py shell -c "from django.core.cache import cache; cache.set('redis_smoke', 1, 60); cache.incr('redis_smoke'); print(cache.get('redis_smoke'))"`

## Rollback Plan

If issues are detected:

1. Stop worker:
   - `docker compose stop bs-worker`
2. Revert to last release that used memcached/previous queue backend.
3. Redeploy previous compose/settings/dependencies.
4. Start services again and verify health.

Note: cache state is ephemeral; rollback can invalidate cached entries but does not affect PostgreSQL durable data.
