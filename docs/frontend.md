# Frontend

- Framework: Angular 21, standalone components with signals and OnPush.
- Structure: `core` (api client, config, guards, interceptors, services), `features/*` per domain, `shared/*` for reusable UI/layouts/pipes/services, `config` for routes/environments, `assets`.
- State: services + signals; no global NgRx; caching via interceptors + IndexedDB.
- API client: generated from `backend/schema.yaml` with `bun run generate:api`; lives in `src/app/core/api`.
- Auth: `auth.interceptor` injects JWT, refreshes on 401 via `AuthService`; logout on repeated failure.
- Caching: `cache.interceptor` + IndexedDB for short-lived GET caching keyed by backend cache version.
- UI: Zard UI primitives plus shared components registry (`docs/shared_components.md`); Tailwind 4 styling.
- Routing: standalone route config in `config`; feature folders lazy-load main domains (customers, products, applications, invoices, payments, reports, dashboard, admin, profile).
- Testing: unit with Vitest; e2e with Playwright + Prism mock server (`bun run dev:mock`).
- Builds: `bun run build` for production; SSR entry `dist/business-suite-frontend/server/server.mjs`; static serve via `bun run serve:static` or Nginx.

## Async transport rules

- Prefer the **generated OpenAPI client** for starting async work.
- Start endpoints should return canonical async `202` payloads (`jobId`, `status`, `progress`, `queued`, `deduplicated`, optional `streamUrl` / `statusUrl` / `requestId`).
- Open SSE only **after** the start call succeeds; if a `streamUrl` is returned, use that URL instead of reconstructing ad hoc endpoints.
- Custom `HttpClient` wrappers are reserved for normalization, request metadata, auth, browser-only concerns, or SSE handling.

## SSE responsibilities

- `SseService` owns:
  - `fetch`-based SSE transport
  - auth headers on initial connect
  - `Last-Event-ID` replay cursor storage
  - optional max-duration rotation handling
  - clean completion vs. error separation
- `reconnectOnComplete(...)` is the pattern for long-running streams that the server rotates after ~55 seconds.
- Long-running consumers such as generic job progress, OCR, categorization, reminders, workflow notifications, and admin maintenance streams should reconnect on completion until they see a terminal payload.

## Request metadata

- The request metadata interceptor injects `X-Request-ID` for normal API calls.
- Async-start flows should also send `Idempotency-Key` so repeated clicks deduplicate cleanly.
- When an API returns `requestId`, preserve it in UI diagnostics/logging so backend and frontend traces can be correlated.

## Focused testing workflow

- Prefer targeted Vitest runs for transport work:
  - `cd frontend && bunx vitest run <spec> --config vitest.config.ts`
- `bun run test:unit` uses Angular's broader test builder and may fail on unrelated spec-type issues before it reaches the target file.
