# GitHub Copilot Project Instructions — BusinessSuite

## Project context

BusinessSuite is a Django-based ERP/CRM for service agencies. It manages customer applications, document workflows (with OCR), tasks, invoicing, and payments.

## Architecture & conventions

- Apps: `customers`, `products`, `customer_applications`, `invoices`, `payments`, `core`.
- Data flow: Products → required document types/tasks → CustomerApplications → Documents → Workflows → Invoices.
- UI: Django templates + Bootstrap 5 + Django Unicorn for reactive UI.
- API: DRF `APIView` classes, token auth (`rest_framework.authtoken`), serializers in `api/serializers/`.
- Forms: Django `ModelForm` + `inlineformset_factory`, render with Crispy Forms and Widget Tweaks.

## Code quality rules (backend)

- Keep views thin; place business logic in models/services/managers.
- Preserve public APIs and existing patterns; avoid breaking changes.
- Model changes must include migrations and any needed admin/form/serializer updates.
- Maintain data integrity for:
  - `Document.completed` logic in `Document.save()` based on `DocumentType` flags.
  - Workflow progression via `DocWorkflow` and due dates using `calculate_due_date()`.
  - Safe deletion checks (e.g., prevent deleting invoiced applications).
- Use `default_storage` for file access and `get_upload_to()` for upload paths.
- Keep settings/secrets in `.env`; do not hardcode credentials.

## Code quality rules (frontend/templates)

- Use Bootstrap 5 classes and existing template blocks; avoid ad‑hoc styling.
- Keep templates consistent with current layout and include `{% load crispy_forms_tags %}` when rendering forms.
- Prefer Django Unicorn components (`components/` folders) for interactive behavior; minimize custom JS.

## Style & consistency

- Python: follow PEP 8, use clear naming, add type hints when obvious.
- Avoid unused imports; keep modules small and single‑responsibility.
- Do not reformat unrelated code; keep diffs minimal.

## Tests & validation

- Update or add tests in the relevant app's `tests/` when changing behavior.
- For API changes, add/adjust DRF tests and serializers.
- Keep fixtures aligned with `fixtures/` when adding core data types.

## When adding features

- Update URLs, views, serializers, permissions, and templates consistently.
- Ensure admin, forms, and API serializers reflect model changes.
- Use existing custom managers (e.g., `DocApplicationManager.search_doc_applications()`) for search logic.

## Documentation & references

- Use the Context7 documentation source when clarifying library behavior.
- Keep README/API docs aligned if endpoints or workflows change.

---

## Frontend Migration to Angular 19 SPA

BusinessSuite is undergoing a migration from Django Templates to a decoupled architecture with Angular 19 + ZardUI frontend. **All new frontend work should follow the migration specifications below.**

### Migration Specification Documents

Reference these documents (located in `copilot/specs/django-angular/`) for guidance on the frontend migration:

#### 📐 [Design Specification](./copilot/specs/django-angular/design.md)

**Use when:** Planning architecture, understanding data flow, choosing implementation patterns.

**Contains:**

- System architecture diagrams (backend/frontend separation)
- Technology stack justification (Angular 19, ZardUI, Bun)
- State management patterns (signals, computed values, service-level state)
- Authentication flow with code examples
- OCR workflow implementation pattern
- Anti-patterns to avoid (with before/after code examples)
- File naming conventions for both frontend and backend

**Key sections to reference:**

- Section 5.1: Backend API Layer patterns
- Section 6: Data Flow & State Management (complete code examples)
- Section 7: Anti-Patterns (what NOT to do)
- Section 8: Migration Strategy (Strangler Fig pattern)

#### 📋 [Requirements Specification](./copilot/specs/django-angular/requirements.md)

**Use when:** Implementing specific features, validating acceptance criteria, handling errors.

**Contains:**

- Functional requirements with test cases (FR-01 to FR-10)
- Non-functional requirements (performance, architecture, tooling)
- API contract examples (OpenAPI, camelCase transformation)
- Authentication & security requirements (hybrid auth, JWT refresh)
- Error handling standards with complete utility code
- Type generation workflow (OpenAPI → TypeScript)
- Form validation error mapping examples

**Key sections to reference:**

- Section 2.1: API Contract examples (how backend/frontend communicate)
- Section 2.2: Authentication patterns (token management, interceptors)
- Section 3.1: Service Layer requirements (keep logic in backend)
- Section 5: Error Handling Standards (global error handler utility)

#### ✅ [Implementation Tasks](./copilot/specs/django-angular/tasks.md)

**Use when:** Starting a new feature, setting up tooling, checking what's been completed.

**Contains:**

- Pre-task and post-task checklists (copy before starting any feature)
- Phase-by-phase implementation plan (Phase 0 through Phase 6)
- Complete setup instructions for:
  - OpenAPI schema generation (`drf-spectacular`)
  - Case transformation (`djangorestframework-camel-case`)
  - Frontend scaffolding (Bun + Angular + ZardUI)
  - API client generation (`@openapitools/openapi-generator-cli`)
- Shared component creation workflow
- Backend preparation steps (query optimization, service layer)

**Key sections to reference:**

- Pre-Task Checklist Template (copy this for every feature)
- Phase 0: Foundation setup (do this first)
- Phase 1: Core architecture (Auth, API generation, shared components)
- Vertical slices (Phases 3-5): Complete feature implementation examples

#### 📦 [API Contract Examples](./copilot/specs/django-angular/api-contract-examples.md)

**Use when:** Implementing API endpoints, generating TypeScript types, understanding request/response formats.

**Contains:**

- Complete OpenAPI schema snippets (YAML format)
- Request/response examples for all major endpoints:
  - Authentication (`/api/token/`, `/api/token/refresh/`)
  - Customer CRUD operations
  - Application management
  - Invoice & payment workflows
  - OCR document upload and polling
- Generated TypeScript interface examples
- Standardized error response formats (400, 401, 403, 404, 500)
- Pagination structure (`count`, `next`, `previous`, `results`)

**Key sections to reference:**

- Section 2: Customer Management (complete OpenAPI schema)
- Section 5: OCR Workflow (async job polling pattern)
- Section 6: Error Responses (consistent format across all endpoints)
- Section 7: Generated TypeScript Interfaces (expected output)

### How to Use These Specifications

1. **Before starting any feature:**
   - Copy the Pre-Task Checklist from [tasks.md](./copilot/specs/django-angular/tasks.md)
   - Review the relevant anti-pattern section in [design.md](./copilot/specs/django-angular/design.md)
   - Check [api-contract-examples.md](./copilot/specs/django-angular/api-contract-examples.md) for the endpoint schema

2. **During implementation:**
   - Reference [requirements.md](./copilot/specs/django-angular/requirements.md) for acceptance criteria and test cases
   - Use code examples from [design.md](./copilot/specs/django-angular/design.md) sections 6 and 7
   - Follow state management patterns exactly as documented
   - Use the error handling utility from requirements.md section 5

3. **After completing a feature:**
   - Update `docs/shared_components.md` if you created reusable components
   - Update `docs/implementation_feedback.md` with lessons learned
   - Run the Post-Task Checklist from [tasks.md](./copilot/specs/django-angular/tasks.md)
   - Verify all tests pass (minimum 80% coverage required)

4. **For API changes:**
   - Update backend serializers to match [api-contract-examples.md](./copilot/specs/django-angular/api-contract-examples.md) patterns
   - Run `bun run generate:api` to regenerate TypeScript clients
   - Never manually write TypeScript interfaces that mirror Django models

5. **For state management:**
   - Use signals (`signal()`, `computed()`) as shown in [design.md](./copilot/specs/django-angular/design.md) section 6.2
   - Never use `BehaviorSubject` or `NgModules`
   - All components must use `ChangeDetectionStrategy.OnPush`

### Migration Phase Status

- [x] Phase 0: Foundation & Documentation Setup
- [x] Phase 1: Core Architecture & Shared Services
- [x] Phase 2: Feature Implementation - Authentication & Dashboard
- [x] Phase 3: Vertical Slice 1 - Customer Management
- [ ] Phase 4: Vertical Slice 2 - Applications & OCR
- [ ] Phase 5: Vertical Slice 3 - Invoices & Payments
- [ ] Phase 6: Integration, Testing, and Cutover

**Current focus:** Phase 4 - Applications & OCR

**Current focus:** Refer to [tasks.md](./copilot/specs/django-angular/tasks.md) for the current implementation phase and next steps.

## OTHER FRONTEND DOCUMENTATION

### QUICK THEME GUIDE

For info on how to maintain and customize the Angular frontend theme, see [THEME GUIDE.md](./copilot/specs/django-angular/THEME_GUIDE.md):

### zardui Documentation and links to component docs

For info on Zard UI component library used in the Angular frontend, see [zardui.md](./copilot/specs/django-angular/zardui.md):
