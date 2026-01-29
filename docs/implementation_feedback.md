# Implementation Feedback Log

## Progress Log

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
