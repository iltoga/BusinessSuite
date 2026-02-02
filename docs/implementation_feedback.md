# Implementation Feedback Log

## Progress Log

- **2026-02-02:** Completed Phase 11 - Integration & Finalization (Feature flagging implemented: `DISABLE_DJANGO_VIEWS` and middleware to protect legacy views; added CSP nonce middleware and tests; added Playwright + axe accessibility tests for key pages)
- **2026-01-24:** Completed Phase 0 - Foundation setup
- **2026-01-24:** Added shared docs registry and custom API exception handler
- **2026-01-24:** Initialized ZardUI and added shared DataTable/ConfirmDialog components
- **2026-01-24:** Added auth/main layouts and GlobalToastService
- **2026-01-24:** Implemented Customer List feature with search, pagination, and status toggling
- **2026-01-25:** Added Application Detail view with OCR polling and shared FileUpload component
- **2026-01-26:** Implemented Products management (list/detail/form), API CRUD for products, and SortableMultiSelect component
- **2026-01-28:** Added CustomerSelect shared component and workflow progression UI for applications
- **2026-01-29:** Implemented Letters (Surat Permohonan) API + Angular form with customer auto-fill
- **2026-01-29:** Implemented Invoices & Payments API + Angular list/detail/form with payment modal
- **2026-01-30:** Added JWT auth claims (roles/groups/is_superuser) and Angular admin-gated delete actions with bulk delete dialogs

## Reuse Hints

- Search, pagination, and expiry badge components are reusable across list views
- FileUpload component can be reused for invoice attachments and payment proofs
- CustomerSelect component works well for pre-filling form fields based on customer selection

## Refactor Requests

- _None yet_

## Technical Debt

- _None yet_

## Wins & Lessons Learned

- SortableMultiSelect simplifies ordered document selection for products and future formsets
- CustomerSelect centralizes async customer lookup, reducing duplicated combobox logic
- Invoice totals remain accurate when using annotated paid/due amounts from API

## Fixes

- **2026-02-01: Full Backup restore fix** ✅
  - Problem: Restoring a "Full Backup" (data + media + users) sometimes failed with a duplicate key error on `django_content_type` during `loaddata` because `post_migrate` re-created `ContentType`/`Permission` rows after a `flush`.
  - Fix: When a backup includes system/user tables, the restore now deletes `ContentType` and `Permission` rows after `flush` and before `loaddata`. Also, `dumpdata` now uses `--natural-foreign` and `--natural-primary` to make future fixtures resilient to contenttype collisions.
  - Files changed: `admin_tools/services.py`
  - How to verify: Take a full backup (include users), restore it to a clean database; verify `loaddata` completes and media files are restored and models reference correct file paths.
  - Note: This prevents regressions caused by automatic `post_migrate` behavior.
