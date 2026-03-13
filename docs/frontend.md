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
