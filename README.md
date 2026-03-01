# 🚀 BusinessSuite (RevisBali CRM/ERP)

BusinessSuite is a Django + Angular ERP/CRM used by visa/document service agencies to manage the full customer lifecycle: onboarding, application processing, document collection/verification, workflow deadlines, invoicing, and payments.

## What the app currently does

- 👥 **Customer Management**
  - Full customer CRUD with search, profile details, active/disabled state, passport metadata.
- 📦 **Product Catalog**
  - Product types, pricing, required/optional documents, and ordered workflow tasks.
- 📝 **Customer Applications**
  - Create applications per customer/product.
  - Track document collection completeness.
  - Track workflow step progression (`pending` → `processing` → `completed` / `rejected`).
  - Reopen and **force-close** application flows (permission-guarded).
- 📅 **Deadline Calendar Integration**
  - Local calendar mirror (`CalendarEvent`) for application deadlines.
  - Automatic Google Calendar sync via PgQueuer background tasks.
  - Optional visa submission window events (for eligible stay-permit products).
- 🧾 **Invoices**
  - Create/edit invoices, link customer applications, generate DOCX/PDF output (sync or async job flow).
  - Smart invoice numbering (`/api/invoices/propose/`).
- 💳 **Payments**
  - Record single payments or full-payment batches across invoice applications.
  - Auto-recalculate `invoice_application` and `invoice` statuses.
- 🛂 **Passport Check Utility**
  - Async OCR/uploadability check via PgQueuer (`/api/customers/check-passport/`).
  - Prompts to update existing customer or create a new customer prefilled from extracted passport fields.
- 📊 **Reports & Admin Tools**
  - KPI dashboards and finance/application pipeline reports.
  - Backups/restore, server-management actions, workflow notifications, push notification tools.

## Tech stack (current)

- **Backend:** Django + Django REST Framework, PostgreSQL
- **Frontend:** Angular 19 standalone SPA (signals + OnPush), Bun, generated OpenAPI clients
- **Queue/Async:** PgQueuer + PostgreSQL
- **Storage:** Django `default_storage` abstraction (local/cloud-compatible)
- **Observability:** structured logs, Loki/Grafana integrations, audit logging options

## Architecture notes

- API endpoints are under `backend/api/` and are consumed by the Angular app in `frontend/`.
- Business logic is primarily in model/service layers (not in templates/components).
- Heavy/async operations (OCR, invoice async generation, calendar sync, notifications) run through PgQueuer tasks.
- Calendar behavior:
  - Local event row is created/updated/deleted first.
  - Google sync is then queued asynchronously by model signals.

## Core lifecycle behavior

### Application lifecycle

At a high level:

1. Create customer
2. Create customer application
3. Upload/validate required documents
4. Progress workflow tasks and deadlines
5. Application reaches completed/ready state
6. Create invoice
7. Record payments until fully paid

Important implementation details:

- `ready_for_invoice` is true when required docs are complete **or** app status is `completed`/`rejected`.
- Force-close is available via `/api/customer-applications/{id}/force-close/` (permissions required).
- Paying an invoice in full marks linked applications as completed.

## Getting started (local)

### 1) Install dependencies

- Python deps (project root / backend env)
- Frontend deps in `frontend/` with Bun

### 2) Configure environment

Create and populate `.env` in the repo root (DB, Redis, external integrations).

### 3) Run DB + Redis infrastructure

Use local docker compose for dependencies (Postgres/Redis/observability stack), then run app services on host.

### 4) Run services

- Backend Django server (`backend/manage.py runserver`)
- PgQueuer worker (`pgq run business_suite.pgqueue:factory`)
- Frontend Angular app (`frontend` Bun start script)

> In VS Code, use the preconfigured tasks (`Start All Services`) to launch backend + worker + frontend together.

## API docs

- OpenAPI schema: `/api/schema/`
- Swagger UI: `/api/schema/swagger-ui/`
- ReDoc: `/api/schema/redoc/`
- Endpoint reference: `docs/API_ENDPOINTS.md`

## User journeys

Detailed business journeys are documented in:

- `user_journeys/journey_01_customer_application_to_invoice_payment.md`
- `user_journeys/journey_02_passport_check_to_direct_invoice.md`

## Additional docs

- `docs/shared_components.md`
- `docs/implementation_feedback.md`
- `docs/playwright-mock-e2e.md`
- `docs/web-push-notifications.md`
- `docs/whatsapp-webhook-tunnel-command.md`

---

If you’re onboarding new contributors, the fastest way is:

1. start all services,
2. open Swagger,
3. follow the journey docs above,
4. then inspect Angular feature folders under `frontend/src/app/features/`.
