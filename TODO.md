# TODO list for business_suite

## BUGS

_No known bugs as of 2026-03-17._

---

## RESOLVED ✓

---

## TODO

### Backend

### Frontend

---

## DONE

- **2026-03-17** — Removed duplicate workflow status constants from
  `backend/customer_applications/models/doc_workflow.py` and migrated backend
  workflow status consumers/tests to use `DocApplication.STATUS_*` as the shared
  source of truth. Added regression coverage for shared status choices and
  terminal completion-date behavior.

- **2026-03-17** — Migrated
  `frontend/src/app/core/services/customers.service.ts` from hand-written
  customer-facing interfaces to generated `core/api/` models where compatible,
  updated customer consumers to use generated types directly, and added service
  regression tests for payload normalization/history mapping.

- **2026-03-17** — Added module- and function-level docstrings to all
  undocumented core service and API view files (11 files total):
  `bulk_delete.py`, `quick_create.py`, `sync_service.py`,
  `calendar_reminder_service.py`, `invoice_service.py`, `view_billing.py`,
  `view_applications.py`, `auth.service.ts`, `sse.service.ts`,
  `customers.service.ts`, `applications.service.ts`.
