# Deployment

## Required Services
- PostgreSQL 18
- Redis 7 (queues + cache)
- Backend API (gunicorn/uvicorn or `manage.py runserver` for dev)
- Dramatiq workers
- Dramatiq scheduler
- Frontend bundle (served via Nginx or `bun run serve:static`)
- Optional observability: Grafana/Alloy or Promtail shipping `logs/` + stdout

## Environment Configuration
- DB: `DB_HOST`, `DB_PORT`, `DB_NAME`, `DB_USER`, `DB_PASS`.
- Redis: `REDIS_URL` or host/port; `DRAMATIQ_REDIS_URL`, `DRAMATIQ_NAMESPACE`, `DRAMATIQ_RESULTS_NAMESPACE` optional overrides.
- Auth: `SECRET_KEY`, `JWT_SIGNING_KEY`.
- Storage: `MEDIA_ROOT`, `MEDIA_URL`, S3 credentials when using `django-storages`.
- External: Google API creds for calendar; AI provider keys for OCR/categorization.
- Flags: `DISABLE_DJANGO_VIEWS`; waffle flags via admin UI.

## Production Topology
- Nginx terminates TLS, serves `frontend/dist/business-suite-frontend`, proxies `/api/` to backend, exposes `/uploads/`.
- Backend runs behind process manager; static collected to `backend/staticfiles` when using WhiteNoise or served by Nginx.
- Dramatiq workers run separately with queue-specific concurrency (see `scripts/run_dramatiq_workers.sh`).
- Scheduler runs as its own process (`python backend/manage.py run_dramatiq_scheduler`).
- Redis hosts queues, results, cache namespaces (see `cache/ARCHITECTURE.md` for DB layout).
- DB backups via `django-dbbackup` to configured backend.

## Scaling
- Horizontal scale backend and workers; ensure Redis/Postgres sizing follows.
- Tune cacheops TTLs and namespace TTLs; monitor Redis memory.
- Use waffle flags for safe rollouts; enable CORS origins per environment.

## VPS Deployment (minimal)
1. Install Docker + compose.
2. Clone repo; create `.env` with production secrets.
3. `docker compose -f docker-compose.yml up -d db redis`.
4. `uv sync`.
5. `uv run python backend/manage.py migrate`.
6. `uv run python backend/manage.py collectstatic --noinput` (if serving static).
7. Start backend (gunicorn recommended), workers (`uv run dramatiq business_suite.dramatiq --queues realtime,default,scheduled,low,doc_conversion`), scheduler.
8. `cd frontend && bun run build`; serve `dist/business-suite-frontend` via Nginx or `bun run serve:static`.
9. Configure Nginx for TLS, API proxy, static/media; ship `logs/` to Grafana/Loki.

## CI/CD Hooks
- Run backend pytest, frontend vitest, Playwright (mock) before deploy.
- Regenerate schema + Angular client; fail build on drift.
- Collect static and run migrations in deploy stage; restart services on success.
