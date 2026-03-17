# GitHub Copilot Instructions — BusinessSuite

## Purpose

Django 6 + Angular 21 ERP/CRM for visa/document-service agencies. Manages customer onboarding → document collection (OCR) → workflow progression → invoicing → payments.

## Stack

| Layer      | Technology                                                                                     |
| ---------- | ---------------------------------------------------------------------------------------------- |
| Backend    | Django 6, DRF, Python 3.14+, SimpleJWT (`Authorization: Bearer`)                               |
| Async      | Dramatiq 2 + Redis broker; queues: `realtime`, `default`, `scheduled`, `low`, `doc_conversion` |
| Frontend   | Angular 21, standalone+OnPush, signals, ZardUI (Tailwind v4), Bun                              |
| DB         | PostgreSQL (source of truth) + Redis (broker/cache/results)                                    |
| API schema | drf-spectacular → `backend/schema.yaml` → generated TS client                                  |

---

## Architecture Overview

```
Angular 21 SPA  →[JWT Bearer]→  DRF APIViews/ViewSets  →  Service layer  →  PostgreSQL
                                         ↓ enqueue actors
                                  Dramatiq + Redis (5 queues)
                                         ↓ workers
                              External APIs (Google, AI/OCR)
```

- **Auth:** `JwtOrMockAuthentication`; interceptor refreshes on 401; mock auth available via env flag.
- **Caching:** `cache.middleware.CacheMiddleware` (per-user namespace) + django-cacheops + Angular `cache.interceptor` (IndexedDB).
- **Realtime:** SSE per-job at `/api/async-jobs/status/{job_id}/` + global Redis Streams multiplexer (`RealtimeEventDispatcherService`).
- **Observability:** Structured logs → `logs/`; optional Alloy/Promtail → Grafana/Loki; auditlog on key models.

---

## Repository Map

```
backend/
  api/              # DRF views + serializers (thin controllers only)
    serializers/    # camelCase ↔ snake_case — one file per domain
    view_billing.py / view_applications.py / view_realtime.py / …
  core/
    services/       # ALL business logic (invoice_service, ai_client, sync_service, …)
    models/         # Base models, CalendarReminder, AsyncJob, etc.
    tasks/          # Dramatiq task actors
  customers/ products/ customer_applications/ invoices/ payments/ letters/ reports/
    # Each app: models.py, admin.py, services/ (domain logic), tests/

frontend/src/app/
  core/
    api/            # AUTO-GENERATED OpenAPI client — DO NOT EDIT MANUALLY
    services/       # Singleton services (auth, sse, job, realtime-notification, …)
    guards/ interceptors/ handlers/
  shared/
    components/     # Reusable UI — see docs/shared_components.md for registry
    layouts/        # MainLayoutComponent, AuthLayoutComponent
    utils/          # form-errors.ts, file-download.ts
  features/         # One folder per domain (customers, applications, invoices, …)
  config/           # app.routes.ts, environment files
```

---

## Code Style & Patterns

### General (Both Stacks)

- **DRY first:** Search for existing implementations before creating anything new.
- **Cleanup is automatic:** After any task, remove unused imports, dead code, debug logs. Report what was removed.
- **No hardcoded credentials:** All secrets via `.env`.

### Backend (Django/Python)

- **Thin views:** Views handle request/response only. All logic in `core/services/` or domain `services/`.
- **Layer rules:** Single-model logic → `model.save()` or model method; cross-model → `core/services/`; query logic → custom managers.
- **Auth:** `DjangoModelPermissions` on ViewSets; `JwtOrMockAuthentication` handles both JWT and dev mock mode.
- **API error format:**
  ```python
  {"code": "validation_error", "errors": {"field": ["message"]}}
  ```
- **File I/O:** Always `default_storage` (supports S3 + local); `get_upload_to()` for paths.
- **N+1 prevention:** `select_related()` / `prefetch_related()` in every list query.
- **Data integrity rules (MUST PRESERVE):**
  - `Document.completed` is auto-calculated in `Document.save()` from `DocumentType.requires_verification`.
  - `DocWorkflow` uses `calculate_due_date()` for scheduling.
  - Applications linked to invoices **cannot be deleted** — validate in service layer.
- **Migrations:** Every model change requires `makemigrations`. Update admin, serializers, tests together.
- **PEP 8 + type hints** on all new code.

### Frontend (Angular/TypeScript)

- **Components:** Always `standalone: true` + `ChangeDetectionStrategy.OnPush`. No `NgModules`.
- **State:** `signal()` for local state, `computed()` for derived values, service-level signals for shared state. **Never `BehaviorSubject`**.
- **File naming:** kebab-case — `customer-list.component.ts`, `auth.service.ts`, `auth.guard.ts`.
- **Template/style extraction:** Extract to `.html`/`.css` only for non-trivial app-specific views. Keep ZardUI wrappers and small components inline.
- **No `localStorage`/`sessionStorage`** — use signals.
- **Notifications:** Inject `GlobalToastService` from `core/services/toast.service.ts`.
- **Error mapping:** `applyServerErrorsToForm(form, error)` + `extractServerErrorMessage(error)` from `shared/utils/form-errors.ts`.

---

## API Integration (Frontend — MANDATORY)

| Rule                                              | Detail                                                                                          |
| ------------------------------------------------- | ----------------------------------------------------------------------------------------------- |
| **Generated client is law**                       | `frontend/src/app/core/api/` is the single source of truth for types and methods                |
| **Never duplicate**                               | Do not create hand-written services that mirror generated endpoints                             |
| **Never hand-write interfaces**                   | Run `bun run generate:api` after backend changes; import from `core/api/`                       |
| **Need a different UI shape?**                    | Adapter/wrapper around generated client — do not bypass it                                      |
| **Manual `fetch`/`HttpClient` allowed only for:** | SSE streams, browser bootstrap before DI, third-party proxies, multipart/progress gaps          |
| **When exception needed:**                        | Isolate in dedicated service + add a comment explaining why the generated client cannot be used |

---

## Testing

### Backend (Django/pytest)

```bash
cd backend && python manage.py test                                # full Django suite
cd backend && uv run pytest                                        # pytest runner
cd backend && python manage.py test core.tests.test_async_job      # single module
```

- Tests in `backend/<app>/tests/` as proper Django test modules.
- **Never** execute `django.setup()`, DB queries, or network calls at import time in `test_*.py` files — wrap in `if __name__ == "__main__":`.
- Mock AI/OCR/Google APIs. Use Django test base classes for DB-backed tests.

### Frontend (Angular/Vitest)

```bash
cd frontend && bun run test                                                       # ng test (Karma)
cd frontend && bun run vitest run                                                  # vitest runner
cd frontend && bun run vitest run src/app/core/services/job.service.spec.ts       # single spec
cd frontend && bun run test:e2e                                                    # Playwright E2E
```

- Unit specs alongside source files (`*.spec.ts`). Mock SSE, API clients, dialogs.
- E2E: Playwright + Prism mock server (`bun run dev:mock`). See `docs/playwright-mock-e2e.md`.
- Minimum 80% frontend unit coverage.

### Before marking complete

1. Run narrowest tests first, then full suite.
2. Fix failing tests — do not skip unless explicitly instructed.
3. Remove debug code and stale fixtures.

---

## New Feature Workflow

1. **Search** existing code (`grep -r`, IDE, `docs/shared_components.md`). Reuse before creating.
2. **Backend:** model → migration → serializer → view → URL → permissions → admin → tests.
3. **Frontend:** service (`core/services/`) → component (`features/<domain>/`) → route (`app.routes.ts`) → help entry (`HelpService`).
4. **API change:** update serializer → regenerate schema → `bun run generate:api` → import from `core/api/`. Never manually sync TS types.
5. **Document:** new shared component → `docs/shared_components.md`; lessons → `docs/implementation_feedback.md`.
6. **Clean up** automatically: unused imports, dead code, debug logs.

### Route pattern (inside `MainLayoutComponent` with `authGuard`)

```typescript
{ path: 'my-feature',          component: MyFeatureListComponent   },
{ path: 'my-feature/new',      component: MyFeatureFormComponent   },
{ path: 'my-feature/:id/edit', component: MyFeatureFormComponent   },
{ path: 'my-feature/:id',      component: MyFeatureDetailComponent },
```

### Service pattern

```typescript
@Injectable({ providedIn: "root" })
export class MyFeatureService {
  private readonly api = inject(MyFeatureApi); // from core/api/
  readonly items = signal<MyFeatureItem[]>([]);
  readonly loading = signal(false);
  async load() {
    this.loading.set(true);
    try {
      this.items.set(
        (await firstValueFrom(this.api.myFeatureList())).results ?? [],
      );
    } finally {
      this.loading.set(false);
    }
  }
}
```

### Component pattern

```typescript
@Component({
  selector: "app-my-feature-list",
  standalone: true,
  templateUrl: "…",
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MyFeatureListComponent implements OnInit {
  private readonly svc = inject(MyFeatureService);
  readonly items = this.svc.items;
  readonly loading = this.svc.loading;
  ngOnInit() {
    this.svc.load();
  }
}
```

---

## Shared Components Catalogue

> Full registry: `docs/shared_components.md` — base path: `frontend/src/app/shared/components/`

| Component                                                      | Selector                                     | Purpose                       |
| -------------------------------------------------------------- | -------------------------------------------- | ----------------------------- |
| `DataTableComponent`                                           | `app-data-table`                             | Sortable, paginated table     |
| `SearchToolbarComponent`                                       | `app-search-toolbar`                         | Search + filter bar           |
| `PaginationControlsComponent`                                  | `app-pagination-controls`                    | Page navigation               |
| `ConfirmDialogComponent`                                       | `app-confirm-dialog`                         | Generic confirmation modal    |
| `BulkDeleteDialogComponent`                                    | `app-bulk-delete-dialog`                     | Bulk delete modal             |
| `FormErrorSummaryComponent`                                    | `app-form-error-summary`                     | Per-form server error list    |
| `JobProgressDialogComponent`                                   | `app-job-progress-dialog`                    | Async job progress modal      |
| `FileUpload` / `MultiFileUpload`                               | `app-file-upload` / `app-multi-file-upload`  | Upload with progress          |
| `CustomerSelect` / `ProductSelect`                             | `app-customer-select` / `app-product-select` | Async search/select           |
| `CalendarIntegration`                                          | `app-calendar-integration`                   | Calendar sync panel           |
| `DetailField` / `DetailGrid` / `CardSection` / `SectionHeader` | various                                      | Detail page layout primitives |

> **Do not edit** ZardUI source files in `shared/components/ui/` — create wrapper components instead.

---

## Dev Commands Reference

```bash
# Infra
docker compose -f docker-compose-local.yml up -d db redis

# Backend
cd backend && uv run python manage.py migrate
cd backend && uv run python manage.py runserver 0.0.0.0:8000
cd backend && uv run dramatiq business_suite.dramatiq --queues realtime,default,scheduled,low,doc_conversion
cd backend && uv run python manage.py run_dramatiq_scheduler

# Frontend
cd frontend && bun install
cd frontend && bun run start          # dev server (proxy to :8000)
cd frontend && bun run start:lan      # dev server (LAN / host 0.0.0.0)
cd frontend && bun run build          # production build
cd frontend && bun run dev:mock       # Prism mock + Angular mock config

# Schema regeneration (preferred)
./refresh-schema-and-api.sh
# or manually:
cd backend && uv run python manage.py spectacular --file schema.yaml
cd frontend && bun run generate:api
```

---

## References

- Shared UI registry: `docs/shared_components.md`
- Lessons learned: `docs/implementation_feedback.md`
- API endpoint list: `docs/API_ENDPOINTS.md`
- Architecture detail: `docs/architecture.md`
- Theme guide: `copilot/specs/django-angular/THEME_GUIDE.md`
- Playwright E2E: `docs/playwright-mock-e2e.md`
- Web push: `docs/web-push-notifications.md`
- Document hooks: `.github/copilot/prompts/create-document-hook.md`
