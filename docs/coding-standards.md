# Coding Standards

- Reuse-first: search existing views/serializers/components before adding new; extend shared components (see `docs/shared_components.md`).
- Thin controllers: keep DRF views slim; put business logic in services/managers/model methods.
- Contract-first: update serializer → regenerate OpenAPI → regenerate Angular client.
- Auth: use `JwtOrMockAuthentication`; enforce permissions; apply throttling scopes on heavy endpoints.
- Naming: Python snake_case; JSON/TypeScript camelCase; queue names and job IDs consistent.
- Module boundaries: keep feature logic inside its app (backend) or feature folder (frontend); shared logic in `core`/`shared`.
- Error handling: use custom exception handler; standardized error payloads; log with context; avoid swallowing Dramatiq retries.
- Logging: structured logs via Logger service; include actor/action identifiers; avoid PII.
- Testing: add pytest for services/serializers/tasks; Vitest for components/services; Playwright for user journeys; keep tests fast (norecursedirs set).
- Migrations: required with model changes; update admin/serializers/tests alongside.
- Frontend UI: standalone components, signals, OnPush; prefer Zard UI primitives; avoid RxJS BehaviorSubject unless necessary.
