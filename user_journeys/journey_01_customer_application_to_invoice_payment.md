# Journey 01 - Customer Application, Invoice Payment, and Internal Processing

This journey documents the standard agency flow for visa/internal-process applications. A paid invoice starts the operational workflow; it does not complete the customer application.

## Preconditions

- User has permission to create customers, applications, invoices, documents, workflows, and payments.
- The product is configured as an internal-process product (`uses_customer_app_workflow=true`) through required documents and/or workflow tasks.
- For dashboard calendar deadlines:
  - `DocApplication.add_deadlines_to_calendar = true`
  - the relevant product task has `add_task_to_calendar = true`

## Step-by-step flow

### 1) Create or select the customer

- UI: `Customers` -> `New Customer`, or open an existing customer.
- API: `POST /api/customers/`.
- Result: customer record is available for applications and invoices.

### 2) Create the customer application

- UI: `Applications` -> `New`, or create from the customer detail view.
- API: `POST /api/customer-applications/`.
- Example product: `XVOA` visa extension.
- Result:
  - application is created for the customer and product
  - required/optional document placeholders are created
  - the first workflow step is created from product task configuration when tasks exist
  - due dates are calculated from the application submission date and task durations

### 3) Upload, validate, and apply documents

- UI: application detail document area.
- User uploads required documents, runs AI validation, reviews the result, and applies accepted documents to the application.
- Result:
  - required document slots become completed
  - the application becomes invoice-ready once required documents are complete
  - invoice readiness does not require workflow completion

### 4) Generate the invoice

- UI: `Invoices` -> `New`, select the customer and eligible customer application.
- API: `POST /api/invoices/`.
- Result:
  - invoice line references the customer application
  - invoice is ready to download/send to the customer
  - the customer application is still not complete

### 5) Send invoice and wait for offline payment

The visa agent sends the invoice to the customer outside the application and waits for payment.

### 6) Record payment

- UI: invoice detail payment modal.
- API: `POST /api/payments/`, or `POST /api/invoices/{id}/mark-as-paid/`.
- Result:
  - invoice application payment status is recalculated
  - invoice status becomes `paid` when fully settled
  - linked internal-process applications are started automatically

When an invoice becomes fully paid, the backend must:

- find linked customer applications whose product has `uses_customer_app_workflow=true`
- ignore product-only invoice lines and invoice-only products
- keep rejected applications rejected
- ensure the first configured workflow task exists
- set the first workflow step to `processing`
- set the customer application to `processing`
- never mark the customer application `completed` because of invoice payment

### 7) Merge documents and submit externally

The agent opens the paid invoice's linked visa applications, merges the prepared documents, and manually uploads them to the immigration website during the external submission process.

### 8) Pay immigration billing and monitor deadlines

After external submission, the agent pays the immigration billing and waits for immigration confirmation. Dashboard calendar and deadline widgets show the currently processing workflow step so the agent can react to biometrics, verification, pickup, or issuance deadlines.

### 9) Complete workflow steps

- UI/API: application detail workflow status controls, dashboard calendar done action, or `POST /api/customer-applications/{id}/workflows/{workflow_id}/status/`.
- When the current step is completed:
  - the completed step is marked `completed`
  - if another task exists, the backend creates/starts the next workflow step as `processing`
  - the customer application remains `processing`
  - if the completed step is the final configured step, the customer application becomes `completed`

## AI and business rules

- Paid invoice does not mean completed application.
- Paid invoice means internal processing may begin.
- The dashboard calendar is driven by active workflow deadlines plus application submission dates.
- `completed` is reserved for fully finished applications after the final workflow step is completed.
- Force-close is a manual exception for already-processed/direct-invoice cases; normal invoice payment must not force-close applications.

## Calendar behavior

- Application submission date is always represented as a calendar event when deadlines are enabled.
- The currently processing calendar-enabled workflow task is represented as the active deadline event.
- Completed workflow tasks may remain visible as done events.
- Active task deadlines disappear only when the application is rejected, calendar deadlines are disabled, no calendar-enabled task exists, or the final workflow step has completed.
