# Journey 02 — Passport Check → New Customer → Direct Invoice (Skip Full Application Workflow)

This journey documents the “already worked visa, invoice now” flow and aligns with current frontend/backend behavior.

## Goal

Create a customer from passport OCR, then create invoice-ready applications directly from invoice form by force-closing them.

---

## Step-by-step flow

### 1) Open Passport Check utility

- UI route: `/utils/passport-check`
- API start: `POST /api/customers/check-passport/` (multipart)
- Processing: async PgQueuer task (`check_passport_uploadability_task`) with progress updates.

### 2) Upload passport and validate

- User uploads passport image.
- System extracts passport fields and validates uploadability.
- On success, UI shows extracted data (name, passport number, nationality, expiration).

### 3) System asks to create/update customer

- If matching customer exists with stale passport data: update dialog appears.
- If customer not found: create dialog appears.

For new-customer path:

- User confirms creation.
- UI navigates to `/customers/new` with prefilled query params from passport extraction.
- User saves customer.

### 4) Go to create invoice

- UI: `Invoices` → `New` (`/invoices/new`)
- Select the customer created in step 3.

### 5) Create customer applications directly from invoice form

- UI action: Quick Add Application modal inside invoice form.
- Behavior (implemented):
  1. Create application (`POST /api/customer-applications/`)
  2. Retrieve application
  3. Force-close application (`POST /api/customer-applications/{id}/force-close/`) when allowed
  4. Return app to invoice form for selection

This is explicitly used to bypass normal document-collection workflow for already-processed cases.

### 6) Add all required applications to the invoice

- Each quick-created app is force-closed and available as line item.
- Invoice line items reference these customer applications.

### 7) Generate invoice

- API: `POST /api/invoices/`
- Optional DOCX/PDF generation via sync/async download endpoints.

### 8) Wait for payment

- Invoice remains in pending/partial state until payments are recorded.

### 9) Update invoice with full payment

- UI: Invoice detail → record payment(s).
- API: `POST /api/payments/`
- If multiple due applications exist, full-payment mode can create all remaining payments in one action.
- Invoice transitions to `paid` when fully settled.

---

## Calendar and workflow notes for this direct-invoice flow

- Force-closed applications are marked `completed` to satisfy invoicing readiness.
- Calendar sync may still run on create/force-close updates if deadline-calendar flags are enabled.
- If deadlines are not needed for this billing-only path, users can keep calendar deadline behavior disabled on those apps.

---

## Consistency checks with current implementation

- ✅ Passport check is async and returns extracted fields used for customer creation flow.
- ✅ Create-from-passport confirmation dialogs exist in UI.
- ✅ Quick application modal explicitly creates then force-closes apps for invoice usage.
- ✅ Payment recording updates invoice and invoice-application statuses automatically.
