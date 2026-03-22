# GitHub Copilot Instructions - BusinessSuite

## Overview / Purpose
BusinessSuite is a Django 6 + DRF backend and Angular 21 frontend for visa/document-service workflows.
Use the dominant pattern in the file you are editing. If the repo has a legacy exception, keep it local and do not normalize it away unless the task explicitly asks for a refactor.
If codebase patterns conflict, prefer the most common implementation and match the surrounding file.

Current stack:
- Backend: Django 6, DRF, SimpleJWT, `djangorestframework-camel-case`, Dramatiq, Redis, PostgreSQL, `django-cacheops`, `django-auditlog`, and `django-waffle`.
- Frontend: Angular 21 standalone components, signals, SSR, Bun, and an OpenAPI-generated client.
- Data/cache: PostgreSQL is the source of truth, Redis is used for broker/cache, and browser IndexedDB is only used where an existing service already uses it.

Cross-check against `README.md`, `docs/architecture.md`, `docs/backend.md`, `docs/frontend.md`, `docs/coding-standards.md`, `docs/shared_components.md`, and `docs/API_ENDPOINTS.md`.

## Backend Guidelines
- DO keep DRF views thin. Standard CRUD lives in `ModelViewSet` classes with `get_queryset()`, `get_serializer_class()`, `perform_create()`, and `perform_update()`.
- DO keep real controller code in the split modules under `backend/api/` such as `view_billing.py`, `view_applications.py`, `view_auth_catalog.py`, `view_notifications.py`, and `view_realtime.py`.
- DO treat `backend/api/views.py` as a compatibility facade only. Add new controller logic in the split module for the domain.
- DO use `backend/api/views_imports.py` and `backend/api/views_shared.py` for shared controller imports, base mixins, pagination, throttles, and helper functions.
- DO keep backend wiring direct. There is no repository layer or DI container in this codebase; services are imported and called directly.
- DO put multi-model orchestration, retries, and IO-heavy work in services. Match the local style: function-based transactional services are common in `backend/core/services/invoice_service.py`, while class-based generators fit places like `backend/products/services/price_list_service.py`.
- DO keep single-model invariants in model methods or `clean()`/`save()` when the codebase already does that. Examples: `backend/customer_applications/models/document.py` and `backend/invoices/models/invoice.py`.
- DO add reusable query logic to `QuerySet` or manager methods when the same filter/search/prefetch shape is reused.
- DO shape querysets with `select_related()` and `prefetch_related()` so serializer fields and computed properties do not trigger extra queries.
- DO use `default_storage` for persisted uploads and generated files. Use direct filesystem calls only for bundled static/template assets or when the existing module already does that for a local asset.
- DO use `ApiErrorHandlingMixin` for API viewsets that need the canonical error payload and cache-throttle resilience. Use `StandardResultsSetPagination` unless the endpoint is a small lookup list.
- DO use the existing search/order pattern on list endpoints: `filters.SearchFilter`, `filters.OrderingFilter`, `search_fields`, and `ordering`.
- DO keep JSON camelCase on the wire. Python stays snake_case, but serializers may intentionally expose aliases such as `updatedBy`, `fullName`, or `jobId`.
- DO enforce access with `IsAuthenticated`, `DjangoModelPermissions`, or the explicit group helpers from `backend/api/permissions.py`: `IsStaffOrAdminGroup`, `IsSuperuserOrAdminGroup`, and `IsAdminOrManagerGroup`. The group names are `admin` and `manager`.
- DO prefer `JwtOrMockAuthentication` for authenticated API endpoints. Mock auth is dev-only and must stay behind `MOCK_AUTH_ENABLED`.
- DO keep the auth token flow consistent with `backend/api/view_auth_catalog.py`: access token in the response body, refresh token in the HttpOnly `bs_refresh_token` cookie, session hint in `bs_refresh_session_hint`, and logout clears both.
- DO keep public/plain Django views for the endpoints that need them: health checks, `public_app_config`, webhooks, SSE streams, and file responses.
- DO annotate custom actions and non-standard payloads with `extend_schema` or `extend_schema_view` so `backend/schema.yaml` stays accurate.
- DO use `build_success_payload()` and `build_error_payload()` when that endpoint family already uses the canonical `{data, meta}` or `{error, meta}` envelope.
- DO use `sse_token_auth_required` plus `StreamingHttpResponse` for SSE endpoints. Use the Redis stream helpers and payload normalizers under `api/utils/stream_payloads.py` and `core/services/redis_streams.py`.
- DO apply the existing throttle scopes and classes on heavy or enqueue-heavy endpoints instead of inventing new ones.
- DON'T move cross-model transactions, file cleanup, or async job orchestration into view methods when an existing service or task already owns that behavior.
- DON'T assume every endpoint returns the same shape. Standard CRUD often returns raw serializer output, custom actions often use the envelope helpers, and streams/file/plain JSON endpoints are separate again.
- DON'T invent new ad hoc error shapes. Use `ValidationError`, `ApiErrorHandlingMixin.error_response()`, or `api.utils.exception_handler.custom_exception_handler`.
- DON'T bypass `default_storage` for upload paths or generated artifacts.
- DON'T force one service style globally. Use the style that matches the module you are editing.

Example backend controller pattern:
```python
class InvoiceViewSet(ApiErrorHandlingMixin, viewsets.ModelViewSet):
    def perform_create(self, serializer):
        from core.services.invoice_service import create_invoice

        invoice = create_invoice(data=serializer.validated_data, user=self.request.user)
        serializer.instance = invoice
```

## Frontend Guidelines
- DO build new UI as standalone components with `ChangeDetectionStrategy.OnPush`. NgModules are not used for new code.
- DO use signals for local mutable state, `computed()` for derived state, `effect()` for side effects, and `rxResource()` for reactive list loading and reloading.
- DO extend `BaseListComponent`, `BaseFormComponent`, or `BaseDetailComponent` for new list/form/detail screens instead of reimplementing navigation, keyboard shortcuts, loading, and delete behavior.
- DO keep app bootstrapping in `frontend/src/app/app.config.ts`. Runtime config, theme initialization, and auth restore belong there or in root services, not in feature components.
- DO use `ConfigService` for runtime config and any bootstrap request that must bypass interceptors. It uses `HttpBackend` on purpose.
- DO use the generated client in `frontend/src/app/core/api/`. Add wrappers in `frontend/src/app/core/services/` only when you need normalization, state, browser-specific behavior, or a nonstandard wire-level flow.
- DO use `AuthService` as the source of truth for auth state. Access tokens stay in memory, refresh tokens come from the HttpOnly cookie, and mock auth stays dev-only.
- DO use `SseService` for SSE. It uses `fetch`, sends auth headers and `Last-Event-ID`, and handles replay and rotation. Do not use `EventSource` directly.
- DO guard browser-only code with `isPlatformBrowser()` or `typeof window !== 'undefined'` because SSR is enabled.
- DO keep routes in `frontend/src/app/app.routes.ts` and follow the existing `list/new/edit/detail` layout. `MainLayoutComponent` is protected by `authGuard`, and products/reports/admin areas use `adminOrManagerGuard`.
- DO update `MenuService` and `HelpService` when adding a screen that appears in navigation or needs contextual help.
- DO reuse shared components from `frontend/src/app/shared/components/`. If you add or change a reusable shared component, update `docs/shared_components.md` in the same change.
- DO use `unwrapApiEnvelope()` and `unwrapApiRecord()` when an endpoint may return raw serializer data or the `{ data, meta }` envelope. Use `extractServerErrorMessage()` and `applyServerErrorsToForm()` for backend validation errors.
- DON'T add NgRx, `BehaviorSubject`, or a new global store for new screens that can be handled with signals and services.
- DON'T edit `frontend/src/app/core/api/**` by hand.
- DON'T add new `localStorage` or `sessionStorage` persistence for general app state. Existing dedicated persistence flows are exceptions, not the default.
- DON'T touch `window`, `document`, `localStorage`, `indexedDB`, or DOM APIs without a browser guard.

Example frontend state pattern:
```ts
protected readonly listResource = rxResource({
  params: () => ({
    query: this.query(),
    page: this.page(),
    pageSize: this.pageSize(),
    ordering: this.ordering(),
    reloadToken: this.reloadToken(),
  }),
  stream: ({ params }) => this.createListLoader(params),
});
```

## Shared Conventions
- Python modules use snake_case. Classes use PascalCase. Legacy CamelCase modules exist (`backend/invoices/services/InvoiceService.py`, `backend/letters/services/LetterService.py`); do not introduce new ones.
- Angular filenames use kebab-case. Selectors follow the existing split: `app-...` for app/shared screens and `z-...` for low-level wrappers and primitives.
- Shared UI components live under `frontend/src/app/shared/components/`. Use `index.ts` barrels and `*.variants.ts` when the component already follows that pattern. Do not edit Zard primitives directly; compose wrappers around them.
- Backend feature logic stays in its Django app. Cross-cutting business logic stays in `core/services`. Frontend feature UI stays in `features/`; reusable UI, services, and state live in `shared/` and `core/`.
- Keep API changes contract-first: update the backend serializer/view, regenerate `backend/schema.yaml`, then regenerate the Angular client with `cd frontend && bun run generate:api`.
- Match the existing API shape for the endpoint family you are editing. Some responses are raw serializer output, some use `{ data, meta }`, and some are streams, files, or plain JSON.
- When adding a navigable screen, update the route, menu, and help registry together if the screen belongs in navigation.
- Keep backend and frontend permissions aligned. Backend group helpers use `admin` and `manager`; frontend guards and menu visibility should mirror those roles.
- `docs/shared_components.md` is the canonical registry for reusable UI. Check it before creating a new component and update it in the same change.
- Use `docs/API_ENDPOINTS.md` to verify exact endpoint names before inventing a new route or action.

## Testing Expectations
- Backend tests use `uv run pytest` as the normal runner.
- Backend test files use the `test_*.py` naming convention and live under `backend/<app>/tests/` or `backend/api/tests/`.
- Use `TestCase` for DB-backed integration tests, `SimpleTestCase` for pure logic, `APIClient` and `APIRequestFactory` for view tests, and `patch()` for external IO, AI, storage, or subprocess calls.
- Keep backend tests isolated from real infrastructure. Use `override_settings`, mocked storage, or request factories when the code path touches the network, Redis, or the filesystem.
- Frontend unit tests use Vitest assertions in `*.spec.ts` files and run through Angular's unit-test builder (`bun run test` / `bun run test:unit`).
- Use `TestBed` when DI, templates, or lifecycle matter. For pure class logic, lightweight harnesses or `Object.create(SomeClass.prototype)` are normal in this repo.
- Use Playwright for end-to-end tests (`bun run test:e2e`).
- Keep browser-specific tests aligned with `frontend/src/test-setup.ts`.
- When changing API contracts, add or update both backend tests and the frontend test that consumes the changed response shape.

Common commands:
```bash
cd backend && uv run pytest
cd frontend && bun run test:unit
cd frontend && bun run test:e2e
cd frontend && bun run dev:mock
```

## Example Files to Follow
### Backend
- `backend/api/view_billing.py` - CRUD viewset with custom actions, service delegation, and canonical envelopes.
- `backend/api/view_applications.py` - queryset shaping, nested prefetching, serializer switching, and OCR/SSE flows.
- `backend/api/view_auth_catalog.py` - token/cookie auth flow, profile actions, and bootstrap endpoints.
- `backend/api/view_realtime.py` - SSE auth and streaming response pattern.
- `backend/api/view_notifications.py` - webhook handling and direct Django/DRF response mix.
- `backend/api/views_shared.py` - `ApiErrorHandlingMixin`, pagination, throttles, and async guard helpers.
- `backend/api/utils/contracts.py` - canonical success/error payload helpers.
- `backend/core/services/invoice_service.py` - transactional multi-model business logic.
- `backend/products/services/price_list_service.py` - class-based document generation service.
- `backend/customer_applications/models/document.py` - model save invariants, storage cleanup, and thumbnail sync.
- `backend/invoices/models/invoice.py` - custom queryset/manager, totals, and document-generation prefetching.
- `backend/core/views.py` - public app-config bootstrap JSON.
- `backend/api/views.py` - compatibility facade only.

### Frontend
- `frontend/src/app/app.config.ts` - bootstrap flow, runtime config, theme initialization, auth restore, and hydration.
- `frontend/src/app/core/services/auth.service.ts` - in-memory JWT auth, refresh-cookie restore, and mock mode.
- `frontend/src/app/core/services/config.service.ts` - bootstrap config fetch via `HttpBackend`.
- `frontend/src/app/core/services/sse.service.ts` - fetch-based SSE with auth headers and replay cursors.
- `frontend/src/app/core/utils/api-envelope.ts` - helpers for raw and enveloped API responses.
- `frontend/src/app/shared/core/base-list.component.ts` - list-page resource and state backbone.
- `frontend/src/app/shared/core/base-form.component.ts` - form lifecycle, validation, keyboard shortcuts, and error mapping.
- `frontend/src/app/shared/core/base-detail.component.ts` - detail lifecycle and guarded delete flow.
- `frontend/src/app/features/customers/customer-list/customer-list.component.ts` - real list screen built on the base list class.
- `frontend/src/app/features/applications/application-list/application-list.component.ts` - more complex list actions, filters, and navigation state.
- `frontend/src/app/shared/components/data-table/data-table.component.ts` - shared table primitive with shortcuts and focus management.
- `frontend/src/app/shared/components/button/button.component.ts` - primitive wrapper and variant pattern.
- `frontend/src/app/shared/components/select/select.component.ts` - CVA select primitive.
- `frontend/src/app/shared/services/menu.service.ts` - role-aware navigation structure.
- `frontend/src/app/shared/services/help.service.ts` - route-driven contextual help registry.
- `docs/shared_components.md` - canonical registry for reusable UI.

## Anti-patterns to Avoid
- Don't add new controller code to `backend/api/views.py` when a split `view_*.py` module is the established home.
- Don't wrap standard CRUD endpoints in a success envelope just for consistency.
- Don't move shared query logic out of managers/querysets into serializers or UI code.
- Don't invent a repository layer or a new global state store; the codebase does not use them.
- Don't bypass `default_storage` for uploads or generated files.
- Don't edit generated `frontend/src/app/core/api/**` by hand.
- Don't use `EventSource` directly for SSE.
- Don't add general app-state persistence to browser storage.
- Don't create a reusable shared UI component without updating `docs/shared_components.md`.
- Don't touch browser globals in SSR paths without a guard.
- Don't assume one response envelope across the whole API; inspect the surrounding endpoint family first.
