# Architecture

```mermaid
graph TD
  Browser[Angular SPA] -->|JWT + JSON| API[DRF API]
  API --> Services[Service layer & managers]
  Services --> Models[(PostgreSQL)]
  Services --> CacheOps[Cache namespace + cacheops]
  API --> Queue[Dramatiq Broker (Redis)]
  Queue --> Workers[Dramatiq Workers]
  Workers --> Models
  Workers --> External[Google APIs / AI OCR]
  Browser --> IDX[IndexedDB cache]
  Logs[Structured Logs] --> Collector[Alloy/Promtail] --> Grafana
```

## System Layers

- Frontend: Angular 21 standalone components, signals, Zard UI; OpenAPI-generated client; cache and auth interceptors; IndexedDB cache keyed by backend version.
- API: DRF with camelCase renderers/parsers; JWT auth via `JwtOrMockAuthentication`; thin views delegating to services/managers.
- Domain apps: customers, products, customer_applications, invoices, payments, letters, reports, admin_tools, cache, core, notifications, landing.
- Async: Dramatiq with Redis broker/results; queues `realtime`, `default`, `scheduled`, `low`, `doc_conversion`; scheduler command `run_dramatiq_scheduler`; tracing middleware.
- Data: PostgreSQL as source of truth; Redis for queues/results/cache namespaces; cacheops for ORM query caching.
- Observability: Structured logging to `logs/` and stdout; auditlog on selected apps; Loki via external collector.

## Notifications Module

The `notifications/` app provides multi-channel message dispatch:

- **Email** — Django `EmailMultiAlternatives` with HTML and plain-text bodies.
- **WhatsApp** — Meta Cloud API (v23.0) with template and free-form text modes; automatic token refresh; webhook processing for delivery status and inbound messages.
- **Web Push** — Firebase Cloud Messaging (FCM) via `firebase-admin`; device token registration; push notification dispatch.

`NotificationDispatcher` routes messages to the appropriate provider based on the `channel` field.
Configuration: `WHATSAPP_*`, `FCM_*` env vars; see `docs/web-push-notifications.md` for web push setup.

## Service Boundaries

- Domain responsibilities live inside their Django app; cross-cutting utilities in `core/services`.
- Cache namespace middleware wraps DRF responses; cacheops handles query caching with per-user isolation.
- External integrations: Google Calendar (via Dramatiq actors), AI OCR/document categorization, Django `default_storage` (S3/local).

## Request Lifecycle

1. Angular client sends JWT-authenticated request.
2. DRF viewset/APIView enforces permissions (DjangoModelPermissions) and throttling.
3. Business logic executes in services/managers/model methods; transactions wrap writes.
4. Responses are camelCased; cache middleware may serve/seed per-user cache; cacheops caches queries.
5. Structured logs emitted; auditlog records model changes when configured.

## Async Workflow Lifecycle

1. Domain event (e.g., document upload) enqueues Dramatiq actor via `db_task`.
2. Redis broker routes to queue (`realtime`, `default`, `scheduled`, `low`, `doc_conversion`).
3. Worker executes with tracing, retries, idempotency locks; progress persisted when applicable.
4. Results stored in Redis results backend (TTL configurable); API polls job status or reads DB state.

## Design Decisions

- Contract-first: DRF schema drives Angular client generation.
- Thin views/service layer keep logic testable and reusable.
- Hybrid caching for per-user isolation + automatic invalidation.
- Async-first for external IO to keep request latency predictable.
- Feature flags via waffle for safe rollouts.
- CSP nonce middleware (Django 6 built-in) toggleable via `CSP_ENABLED` / `CSP_MODE`; Cloudflare-compatible.
- Local-resilience sync for offline/multi-node deployments; see `docs/sync-local-resilience.md`.

## Suitability

Visa/document workflows depend on external APIs and heavy processing; Dramatiq decouples latency and provides retries. Frequent user-scoped reads benefit from namespace + cacheops caching. Contract-first APIs reduce frontend/backward compatibility risk. Angular standalone components and shared registry keep UI consistent while enabling rapid feature delivery.
