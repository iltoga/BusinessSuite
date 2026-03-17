# TODO list for business_suite

## BUGS

_No known bugs as of 2026-03-17._

---

## RESOLVED ✓

---

## TODO

### Backend

- **`customer_applications/models/doc_workflow.py` line 26** — Remove duplicate
  status constants (`STATUS_COMPLETED`, `STATUS_REJECTED`, `STATUS_PENDING`,
  `STATUS_PROCESSING`) from `DocWorkflow`. Identical constants already exist on
  `DocApplication`; `DocWorkflow` should reference `DocApplication.STATUS_*` or
  a shared `AppStatus` enum to avoid drift.

### Frontend

- **`frontend/src/app/core/services/customers.service.ts`** — Migrate legacy
  hand-written interfaces (`CustomerListItem`, `CustomerDetail`,
  `UninvoicedApplication`, `CustomerApplicationHistory`, `CountryCode`,
  `PaginatedResponse`) to the generated types from `core/api/` wherever the
  shapes are compatible. See module docstring for migration guidance.

---

## DONE

- **2026-03-17** — Added module- and function-level docstrings to all
  undocumented core service and API view files (11 files total):
  `bulk_delete.py`, `quick_create.py`, `sync_service.py`,
  `calendar_reminder_service.py`, `invoice_service.py`, `view_billing.py`,
  `view_applications.py`, `auth.service.ts`, `sse.service.ts`,
  `customers.service.ts`, `applications.service.ts`.
