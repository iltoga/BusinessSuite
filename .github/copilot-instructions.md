# GitHub Copilot Instructions — BusinessSuite

## What is BusinessSuite?

BusinessSuite is a Django-based ERP/CRM for service agencies specializing in visa applications and document processing. It manages the complete customer journey: from initial inquiry through document collection (with OCR validation), workflow progression, invoicing, and payment tracking.

**Target users:** Service agency staff processing visa applications, managing customer relationships, and handling financial transactions.

**Key features:** Customer management, product catalog, application workflows, document OCR, task management, invoicing, payment tracking.

---

## Technology Stack

### Backend

- **Framework:** Django>=6.0.0
- **API:** Django REST Framework (DRF) 3.16.x with token authentication
- **Database:** PostgreSQL
- **File Storage:** Django default_storage abstraction
- **OCR:** Custom OCR/AI engine integration

### Frontend (Legacy - Being Migrated)

- **Templates:** Django Templates + Bootstrap 5
- **Reactive UI:** Django Unicorn components
- **Forms:** Django ModelForm + Crispy Forms + Widget Tweaks

### Frontend (New - Angular Migration In Progress)

- **Framework:** Angular 19+ (standalone components, signals)
- **UI Library:** ZardUI (Tailwind CSS v4, shadcn-like architecture)
- **Package Manager:** Bun
- **State Management:** Angular signals (NOT RxJS BehaviorSubject)
- **Build Tool:** Angular CLI with Bun

---

## Project Structure

```
businesssuite/
├── customers/              # Customer CRUD, search, profiles
├── products/               # Product catalog, pricing
├── customer_applications/  # Application workflows, documents
│   └── components/        # Django Unicorn reactive components
├── invoices/              # Invoice generation, calculations
├── payments/              # Payment recording, tracking
├── core/                  # Shared utilities, base models
│   ├── services/         # Business logic layer
│   └── managers/         # Custom Django model managers
├── api/
│   ├── serializers/      # DRF serializers (camelCase output)
│   └── views/            # DRF APIView and ViewSet classes
├── frontend/             # Angular 19 SPA (migration in progress)
│   ├── src/app/
│   │   ├── core/         # Singleton services, guards, interceptors
│   │   ├── shared/       # Reusable components, layouts, utilities
│   │   └── features/     # Lazy-loaded feature modules
│   └── docs/             # Frontend-specific documentation
└── copilot/
    └── specs/django-angular/  # Migration specification documents
```

---

## Code Quality Standards

### General Principles

#### DRY and Component Reusability (CRITICAL)

**Before creating ANY new view, component, or service:**

1. **Search the codebase** for similar existing implementations
2. **Analyze if the existing code can be:**
   - Used as-is with minor configuration
   - Updated to be reusable without breaking current functionality
   - Extended through inheritance or composition
3. **If reusable code exists:**
   - Use it directly, OR
   - Refactor it to be generic (add parameters, make it configurable)
   - Document the change in the relevant `docs/` file
4. **If creating new code:**
   - Design it to be reusable from the start
   - Add it to `docs/shared_components.md` (frontend) or document in docstrings (backend)

**Examples:**

- Before creating a new data table component, check `frontend/src/app/shared/components/`
- Before creating a new DRF serializer, check if a similar one exists in `api/serializers/`
- Before creating a new Django form, check existing forms in the same app

#### Code Cleanup (AUTOMATIC)

**After completing any task:**

1. **Identify and remove:**
   - Unused imports
   - Dead code (functions, methods, classes not referenced anywhere)
   - Temporary/debug code (console.logs, print statements, commented code blocks)
   - Stale test fixtures or test data
2. **Consolidate:**
   - Duplicate code into reusable functions
   - Similar patterns into shared utilities
3. **Do NOT ask for permission** — perform cleanup automatically within the same response
4. **Report what was cleaned:**
   ```
   ✅ Task completed
   🧹 Cleaned up:
   - Removed 3 unused imports from customer_service.py
   - Deleted stale CustomerFormOld component
   - Consolidated duplicate validation logic into validate_phone_number()
   ```

### Backend (Django)

#### Views and Business Logic

- **Keep views thin** — controllers should delegate to services/managers
- **Business logic belongs in:**
  - `models.py` for single-model operations (e.g., `Document.mark_as_complete()`)
  - `core/services/` for complex multi-model operations (e.g., invoice calculations)
  - Custom managers for query logic (e.g., `DocApplicationManager.search_doc_applications()`)
- **Never put business logic in:**
  - Templates
  - Serializers (only data transformation)
  - Views (only request/response handling)

#### Data Integrity Rules (MUST PRESERVE)

- `Document.completed` is auto-calculated in `Document.save()` based on `DocumentType.requires_verification` flag
- Workflow progression via `DocWorkflow` uses `calculate_due_date()` for scheduling
- Applications linked to invoices cannot be deleted (add validation check)
- Use `default_storage.open()` for file access, `get_upload_to()` for upload paths

#### API Standards

- Use DRF `APIView` or `ModelViewSet` classes
- Token authentication: `rest_framework.authtoken`
- Serializers in `api/serializers/` handle camelCase ↔ snake_case transformation
- Return standardized error format:
  ```python
  {
      "code": "validation_error",
      "errors": {"field": ["message"]}
  }
  ```

#### Database and Migrations

- All model changes **require migrations**
- Update related components when models change:
  - Admin configuration
  - Forms
  - Serializers
  - Tests
- Use `select_related()` and `prefetch_related()` to prevent N+1 queries

#### Security and Configuration

- **Never hardcode credentials** — use environment variables via `.env`
- Use `default_storage` abstraction for file operations (supports S3, local, etc.)
- Validate permissions before file downloads
- Follow PEP 8, add type hints where obvious

### Frontend (Angular Migration)

#### Component Architecture

- **ALWAYS use standalone components** — no `NgModules`
- **ALWAYS use `ChangeDetectionStrategy.OnPush`**
- **State management:**
  - Use `signal()` for local component state
  - Use `computed()` for derived values
  - Use service-level signals for shared state
  - **NEVER use `BehaviorSubject` or RxJS subjects for state**

#### Before Creating New Components

1. Check `docs/shared_components.md` for existing components
2. If similar exists:
   - Extend it with new inputs/outputs
   - Make it more generic if needed
   - Update documentation
3. If creating new:
   - Make it reusable (accept inputs, emit outputs)
   - Add to `docs/shared_components.md` immediately
   - File separation guidance: extract templates/styles into separate files (`.ts`, `.html`, `.css`) **only for app-specific components and views (pages)** that contain non-trivial markup or represent distinct views. **Do not** extract templates/styles for third-party library components (e.g., ZardUI), small UI-only components, or trivial templates—keep those inline to avoid unnecessary churn.
   - When extraction is needed, do it in small, reviewable batches (2–3 components per PR) and document the change in `docs/shared_components.md` to keep the codebase consistent and reviewable.

#### API Integration

- **NEVER manually write TypeScript interfaces** that mirror Django models
- **ALWAYS use generated clients:**
  1. Update Django serializer
  2. Run `bun run generate:api` in `frontend/`
  3. Import from `src/app/core/api/`
- Use error handling utility from `shared/utils/error-handler.ts`
- Map API errors to form controls using `mapApiErrorsToForm()`

#### File Naming

- Components: `customer-list.component.ts` (kebab-case)
- Services: `auth.service.ts` (kebab-case)
- Interfaces: `customer.interface.ts` (kebab-case)
- Guards: `auth.guard.ts` (kebab-case)

### Frontend (Legacy Django Templates)

- Use Bootstrap 5 utility classes, avoid custom CSS
- Include `{% load crispy_forms_tags %}` when rendering forms
- Prefer Django Unicorn components for interactivity over custom JavaScript
- Keep templates consistent with existing layout blocks

### Testing

- Update or add tests in `tests/` when changing behavior
- For API changes: add DRF tests and serializer tests
- For models: test business logic and constraints
- Maintain fixtures in `fixtures/` for core data types
- **Frontend:** Minimum 80% test coverage required
- **E2E tests:** Use Playwright with the mock server (Prism). See `docs/playwright-mock-e2e.md` for setup, recommended `playwright.config.ts`, examples, CI tips, and troubleshooting.

---

## Development Workflow

### When Adding Features

**Step 1: Research existing code (MANDATORY)**

```bash
# Search for similar components
grep -r "similar_pattern" .
# or use IDE search for class/function names
```

**Step 2: Check documentation**

- Frontend: Review `copilot/specs/django-angular/` specifications
- Check `docs/shared_components.md` for reusable UI components
- Review `docs/implementation_feedback.md` for lessons learned

**Step 3: Plan implementation**

- Can I reuse existing code?
- If yes: refactor for reusability
- If no: design new code to be reusable

**Step 4: Implement consistently**

- Update URLs, views, serializers, permissions, templates
- Ensure admin, forms, and API serializers reflect model changes
- Use existing patterns (e.g., `DocApplicationManager.search_doc_applications()`)

**Step 5: Document**

- Add new shared components to `docs/shared_components.md`
- Update `docs/implementation_feedback.md` with learnings

**Step 6: Clean up (AUTOMATIC)**

- Remove unused imports, dead code, debug statements
- Consolidate duplicates
- Report cleanup actions

### For API Changes

1. Update Django serializer with new fields/logic
2. Ensure OpenAPI schema is current (`drf-spectacular`)
3. Run `bun run generate:api` to regenerate TypeScript clients
4. Never manually sync TypeScript interfaces

### For Database Changes

1. Create migration: `python backend/manage.py makemigrations`
2. Update admin.py if needed
3. Update serializers if exposed via API
4. Update forms if used in templates
5. Add/update tests

---

## Angular Migration (In Progress)

BusinessSuite is migrating from Django Templates to a decoupled Angular 19 SPA frontend. **All new frontend work should follow the migration specifications.**

### Migration Specification Documents

Located in `copilot/specs/django-angular/`:

#### 📐 [Design Specification](copilot/specs/django-angular/design.md)

**Use when:** Planning architecture, understanding data flow, choosing implementation patterns.

**Key sections:**

- Section 5.1: Backend API Layer patterns
- Section 6: Data Flow & State Management (complete code examples)
- Section 7: Anti-Patterns (what NOT to do) — **READ THIS FIRST**
- Section 8: Migration Strategy (Strangler Fig pattern)

#### 📋 [Requirements Specification](copilot/specs/django-angular/requirements.md)

**Use when:** Implementing features, validating acceptance criteria, handling errors.

**Key sections:**

- Section 2.1: API Contract examples (backend ↔ frontend communication)
- Section 2.2: Authentication patterns (JWT, interceptors)
- Section 3.1: Service Layer requirements (keep logic in backend)
- Section 5: Error Handling Standards (global error handler utility)

#### ✅ [Implementation Tasks](copilot/specs/django-angular/tasks.md)

**Use when:** Starting a new feature, setting up tooling, tracking progress.

**Key sections:**

- **Pre-Task Checklist Template** — copy this before EVERY feature
- Phase 0: Foundation setup
- Phase 1: Core architecture (Auth, API generation, shared components)
- Vertical slices: Complete feature implementation examples

#### 📦 [API Contract Examples](copilot/specs/django-angular/api-contract-examples.md)

**Use when:** Implementing API endpoints, generating TypeScript types, understanding request/response formats.

**Contains:**

- Complete OpenAPI schema snippets (YAML)
- Request/response examples for all endpoints
- Generated TypeScript interface examples
- Standardized error response formats

### Migration Workflow

**Before starting ANY Angular feature:**

1. Copy Pre-Task Checklist from [tasks.md](copilot/specs/django-angular/tasks.md)
2. Review anti-patterns in [design.md](copilot/specs/django-angular/design.md) Section 7
3. Check [api-contract-examples.md](copilot/specs/django-angular/api-contract-examples.md) for endpoint schema
4. Search [docs/shared_components.md](../docs/shared_components.md) for reusable components

**During implementation:**

1. Follow state management patterns from [design.md](copilot/specs/django-angular/design.md) Section 6.2
2. Use error handling utility from [requirements.md](copilot/specs/django-angular/requirements.md) Section 5
3. Use generated API clients — NEVER manual TypeScript interfaces
4. All components must use `ChangeDetectionStrategy.OnPush`

**After completing a feature:**

1. Update [docs/shared_components.md](../docs/shared_components.md) if reusable components created
2. Update [docs/implementation_feedback.md](../docs/implementation_feedback.md) with lessons learned
3. Run Post-Task Checklist from [tasks.md](copilot/specs/django-angular/tasks.md)
4. **Automatic cleanup:** Remove unused code, imports, debug statements
5. Verify tests pass (minimum 80% coverage)

### Critical Angular Migration Rules

❌ **NEVER:**

- Use `NgModules` for features
- Use `BehaviorSubject` for state
- Manually write TypeScript interfaces for Django models
- Put business logic in components
- Use `localStorage` or `sessionStorage` in Angular (use signals)

✅ **ALWAYS:**

- Use standalone components
- Use `signal()` and `computed()` for state
- Run `bun run generate:api` after backend changes
- Keep business logic in Django backend
- Use `ChangeDetectionStrategy.OnPush`

### Migration Phase Status

- [x] Phase 0: Foundation & Documentation Setup
- [x] Phase 1: Core Architecture & Shared Services
- [x] Phase 2: Authentication & Dashboard
- [x] Phase 3: Customer Management
- [x] Phase 4: Application Detail & OCR
- [x] Phase 5: Products Management
- [x] Phase 6: Customer Applications List & CRUD
- [x] Phase 7: Letters (Surat Permohonan)
- [x] Phase 8: Invoices & Payments
- [x] Phase 9: Admin & Maintenance Tools (COMPLETED)
- [x] Phase 10: User Profile View (NEW FEATURE - ANGULAR EXCLUSIVE) (COMPLETED)
- [x] Phase 11: Integration & Finalization

**Current focus:** Completed: Integration & Finalization (Phase 11)

---

## Additional Frontend Documentation

### Theme Customization

**Canonical theme guide:** See [THEME_GUIDE.md](copilot/specs/django-angular/THEME_GUIDE.md) — this file is the single source of truth for colors, button variants, and theme behavior. All frontend work, specs, and automated checks should reference it to keep the style consistent.

### ZardUI Component Library

See [zardui.md](copilot/specs/django-angular/zardui.md) for documentation on the ZardUI component library and links to component-specific docs.

---

## Available Development Tools

### Backend Scripts

- `python backend/manage.py runserver` — Start development server
- `python backend/manage.py makemigrations` — Create database migrations
- `python backend/manage.py migrate` — Apply migrations
- `python backend/manage.py test` — Run test suite
- `python backend/manage.py shell` — Django Python shell

### Frontend Scripts (Angular)

- `cd frontend && bun install` — Install dependencies
- `bun run dev` — Start dev server with proxy to Django backend
- `bun run generate:api` — Regenerate TypeScript API clients from OpenAPI
- `bun run build` — Production build
- `bun run test` — Run tests

### Common Commands

- Search for existing implementations: `grep -r "pattern" .`
- Find unused imports (Python): Use IDE or `pylint`
- Check test coverage: `python backend/manage.py test --coverage`

---

## References and Resources

- **API Endpoints:** See `docs/API_ENDPOINTS.md` for a list of main API endpoints (note: update it as new endpoints are added)
- **Web Push Notifications:** See `docs/web-push-notifications.md` for setup and usage guide.
- **Context7 Documentation:** Reference for library behavior clarification
- **Django REST Framework Docs:** https://www.django-rest-framework.org/
- **Angular 19 Docs:** https://angular.dev/
- **ZardUI Components:** See `copilot/specs/django-angular/zardui.md`

---

## Summary for AI Agents

This is a Django + Angular ERP/CRM for visa processing agencies. Key priorities:

1. **DRY Principle:** Always search for and reuse existing code before creating new code
2. **Service Layer:** Business logic in `core/services/`, not in views or components
3. **Data Integrity:** Preserve workflow rules, deletion constraints, and auto-calculations
4. **Angular Migration:** Use specifications in `copilot/specs/django-angular/`, follow anti-patterns guide
5. **Generated Clients:** Use OpenAPI → TypeScript generation, never manual interfaces
6. **Automatic Cleanup:** Remove unused/stale code after every task without asking
7. **Documentation:** Update [docs/shared_components.md](../docs/shared_components.md) and [docs/implementation_feedback.md](../docs/implementation_feedback.md)

When in doubt, check the migration specs in `copilot/specs/django-angular/` — they contain complete working examples for every pattern.
