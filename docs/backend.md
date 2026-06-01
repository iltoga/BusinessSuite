# Backend

- Framework: Django 6 + DRF; Python 3.12+.
- Apps: `core`, `cache`, `customers`, `products`, `customer_applications`, `invoices`, `payments`, `letters`, `reports`, `admin_tools`, `landing`.
- API endpoints: defined in `api/` module (not a Django app).
- Notification providers: `notifications/services/` (not a separate Django app).
- Models: domain models per app; audit logging enabled for customers/products/invoices/customer_applications.
- Services: `core/services/*` host business logic (AI client, Redis client, app settings, storage helpers, logger).
- API: DRF viewsets/APIViews under `backend/api`; camelCase serializers; throttling scopes for OCR, cron, invoice jobs; exception handler `api.utils.exception_handler.custom_exception_handler`.
- Authentication: JWT via SimpleJWT (`JwtOrMockAuthentication`), `Authorization: Bearer`; optional mock auth (env driven) for demos; session auth for admin.
- Validation: serializer validation plus service-level guards; invoice/application relationships protected; file access through `default_storage`.
- Caching: middleware `cache.middleware.CacheMiddleware` + cacheops; Redis DB allocation per `cache/ARCHITECTURE.md`; per-user namespace prefixing.
- OpenAPI: drf-spectacular with preprocessing hooks to include serializer metadata; schema at `/api/schema/`.
- Settings highlights:
  - Host/Redis resolution adapts to Docker vs host.
  - CORS via env; default localhost + APP_DOMAIN variants.
  - SimpleJWT lifetimes: 15 min access (configurable via `JWT_ACCESS_TOKEN_LIFETIME_MINUTES`), 7 days refresh.
  - DRAMATIQ namespace/results namespaces configurable; workers default counts in settings.
- Logging: structured logging via Logger service; performance middleware; logs in `logs/`.
- Runtime toggles: backend settings and environment overrides.
- Tests: pytest with strict markers; e2e Redis/Dramatiq tests; caching and task runtime policies covered.

## Canonical async controller pattern

- Async **start** endpoints should return `202 Accepted` JSON, not immediately treat the SSE endpoint as the trigger.
- Build start payloads from the shared async helpers so callers receive a consistent contract: `jobId`, `status`, `progress`, `queued`, `deduplicated`, optional `requestId`, `statusUrl`, `streamUrl`, and `downloadUrl`.
- Keep heavy orchestration in services/tasks; views should only validate input, claim idempotency, enqueue work, and shape the response.

## Stream publication path

- The production path for user-facing progress is DB state → signal/service publish → Redis Streams → SSE.
- Preserve `transaction.on_commit()` publication patterns so streams do not race ahead of committed database state.
- Domain SSE endpoints should align on replay behavior, keepalive handling, and terminal-event semantics.

## Idempotency and conflict behavior

- Async controllers should accept `Idempotency-Key` and fingerprint the request payload/query.
- Same key + same fingerprint => return the cached job identity with `deduplicated=true`.
- Same key + different fingerprint => return **`409 Conflict`** using the canonical error payload.
- When possible, include `requestId` in start responses and stream payloads so traces can be correlated across layers.

## SSE operational guidance

- Several SSE endpoints are deliberately rotated around **55 seconds**; frontend consumers are expected to reconnect on clean completion.
- Replay should honor `Last-Event-ID`, and replay-first admin/domain URLs may also expose explicit query params such as `replay=1` and `job_id=<id>`.
- Keepalive comment frames are part of normal operation and should not be interpreted as data events.

## Bootstrap safety

- Keep Dramatiq bootstrap/import paths free of database-dependent settings reads.
- Resolve DB-backed runtime settings lazily after Django is ready or inside task/runtime code, not at module import time.
- Treat this as an import-safety rule for `business_suite/dramatiq.py` and related worker bootstrap code.
