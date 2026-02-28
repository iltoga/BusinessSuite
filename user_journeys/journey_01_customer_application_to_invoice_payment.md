# Journey 01 — New Customer → Application Lifecycle → Invoice → Full Payment

This journey documents the standard operational flow and aligns with current backend + Huey + frontend logic.

## Preconditions

- User has permission to create customers, applications, invoices, and payments.
- Product is configured with workflow tasks and required documents.
- If calendar sync is desired:
  - `DocApplication.add_deadlines_to_calendar = true`
  - Relevant task(s) have `add_task_to_calendar = true`

---

## Step-by-step flow

### 1) Create a new customer

- UI: `Customers` → `New Customer` (`/customers/new`)
- API: `POST /api/customers/`
- Result: customer record is created and can be used in applications/invoices.

### 2) Create a new customer application

- UI: `Applications` → `New` (`/applications/new`) or from customer detail.
- API: `POST /api/customer-applications/`
- Result:
  - Application is created with initial workflow step.
  - Due dates are computed from task durations (`calculate_due_date` logic).

**Calendar note:**
When the app is created/updated, backend queues `sync_application_calendar_task` (Huey). This updates local `CalendarEvent` and then queues Google Calendar sync.

### 3) Upload required documents

- UI: Application detail/document actions.
- API: document CRUD under `/api/documents/`.
- Result:
  - Required docs are tracked as completed/incomplete.
  - `ready_for_invoice` becomes true when required docs are complete, or if status is already completed/rejected.

### 4) First deadline — biometrics appointment

- Business expectation: first task is typically “go to immigration for biometrics”.
- System behavior:
  - This is represented by **task step configuration**, not hardcoded text.
  - If that task has `add_task_to_calendar = true`, the event is created/updated.

**Calendar note:**
At this action, a calendar event is maintained in both:

- local calendar mirror (`CalendarEvent` table), and
- Google Calendar (asynchronously via Huey sync tasks).

### 5) Advance workflow to next step

- UI/API: update workflow status or use advance workflow actions.
  - `POST /api/customer-applications/{id}/advance-workflow/`
  - or `POST /api/customer-applications/{id}/workflows/{workflow_id}/status/`
- Result:
  - Current step transitions, next step becomes active.
  - Due date recalculates for the next task.

### 6) Second/final deadline — immigration verification (2–4 days wait)

- Business expectation: second task is often “wait 2–4 days for immigration verification/visa issuance”.
- System behavior:
  - Duration comes from product task config (`duration`, `duration_is_business_days`).
  - If configured as 2–4 days, system deadline follows that exact setting.

**Calendar note:**
As with step 4, the next-task deadline is mirrored locally and synced to Google Calendar via background tasks.

### 7) Application completes

- Completion can happen by workflow progression and document/workflow status logic.
- UI shows app status `completed`; app becomes invoice-ready.

### 8) Generate invoice

- UI: `Invoices` → `New` (`/invoices/new`) and select customer applications.
- API: `POST /api/invoices/`
- Optional document generation:
  - sync: `GET /api/invoices/{id}/download/?file_format=docx|pdf`
  - async: `POST /api/invoices/{id}/download-async/`

### 9) Wait for payment

- Invoice status typically moves through `pending_payment` / `partial_payment` depending on payment records.

### 10) Update invoice with full payment

- UI: Invoice detail → record payment(s) (`Payment Modal`).
- API: `POST /api/payments/` (single or multiple invoice-application payments).
- Result:
  - Invoice application statuses recalculate.
  - Invoice status becomes `paid` when fully settled.
  - Linked applications are kept/marked completed.

---

## Consistency checks with current implementation

- ✅ Force-close exists but is not required for this standard journey (`POST /api/customer-applications/{id}/force-close/`).
- ✅ Calendar is async and resilient (local mirror first, Google sync queued).
- ✅ Payment updates auto-propagate invoice status changes.
