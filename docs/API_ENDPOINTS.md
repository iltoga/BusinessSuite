# API Endpoints Documentation

This document lists the main API endpoints exposed by the application in this repository, including their payload (input parameters/files) and a short description for each.

> **Note:** This list is kept in sync with the URL patterns in `api/urls.py` and the view actions in `api/views.py`. For the most complete and up-to-date list, consult the browsable API or the OpenAPI schema at `/api/schema/`.

---

## Authentication ✅

- **POST `/api/api-token-auth/`**
  - **Input:** `{ "username": string, "password": string }`
  - **Description:** Obtain a JWT token (custom TokenObtainPair-backed view).

- **GET `/api/session-auth/`**
  - **Input:** Session credentials (browser-based login)
  - **Description:** Session-based auth endpoints exposed by DRF.

- **GET `/api/mock-auth-config/`**
  - **Input:** None
  - **Description:** Return mock authentication claims when `MOCK_AUTH_ENABLED` is true (used by frontend dev mode).

---

## API Schema & Docs 🔧

- **GET `/api/schema/`** — OpenAPI schema (drf-spectacular)
- **GET `/api/schema/swagger-ui/`** — Swagger UI
- **GET `/api/schema/redoc/`** — ReDoc UI

---

## Country Codes 🌐

- **GET `/api/country-codes/`**
  - **Description:** List of ISO country codes used for nationality dropdowns (no pagination). Requires authentication.

---

## Customers 👥

- **GET `/api/customers/`**
  - **Input:** Query params: `q`/`search`, `hide_disabled` (true/false), `page`, `page_size`
  - **Description:** Paginated list of customers.

- **GET `/api/customers/search/?q=<query>`**
  - **Description:** Compatibility search endpoint used by templates and frontend.

- **GET `/api/customers/<id>/`**
  - **Description:** Retrieve a single customer.

- **POST `/api/customers/quick-create/`**
  - **Input:** Minimal customer payload (see `CustomerQuickCreateSerializer`)
  - **Description:** Create a customer quickly (returns a small payload for client-side use).

- **POST `/api/customers/<id>/toggle-active/`**
  - **Description:** Toggle `active` flag for a customer.

- **POST `/api/customers/bulk-delete/`**
  - **Permissions:** Superuser-only
  - **Description:** Bulk delete customers by query.

---

## Products 🧾

- **GET `/api/products/`**
  - **Input:** Query params: `search`, `product_type`
  - **Description:** Paginated list of products.

- **GET `/api/products/get_product_by_id/<product_id>/`**
  - **Description:** Returns `product`, `required_documents`, and `optional_documents` (document type objects).

- **GET `/api/products/get_products_by_product_type/<product_type>/`**
  - **Description:** Return products of a specific `product_type`.

- **POST `/api/products/quick-create/`**
  - **Input:** Minimal product payload (see `ProductQuickCreateSerializer`)
  - **Description:** Create a product quickly for client-side flows.

- **GET `/api/products/<id>/can-delete/`**
  - **Description:** Check whether a product can be deleted safely.

- **POST `/api/products/bulk-delete/`**
  - **Permissions:** Superuser-only
  - **Description:** Bulk delete products by query.

---

## Document Types & Documents 📄

- **GET `/api/document-types/`**
  - **Description:** List document types.

- **GET `/api/document-types/<id>/can-delete/`**
  - **Description:** Check whether a document type can be safely removed (ensures no products reference it).

- **GET `/api/documents/`**, **POST `/api/documents/`**, **PATCH `/api/documents/<id>/`**
  - **Description:** Standard CRUD for document records. Note: file uploads expect multipart form data.

- **GET `/api/documents/<id>/download/`**
  - **Description:** Stream/download the stored document file (authenticated).

- **GET `/api/documents/<id>/print/`**
  - **Description:** Return document print data including nested application/customer/product info.

- **POST `/api/documents/merge-pdf/`**
  - **Input:** JSON: `{ "document_ids": [1,2,3] }`
  - **Description:** Merge completed document files into a single PDF and return it as a download.

- **POST `/api/documents/<id>/actions/<action_name>/`**
  - **Description:** Execute a registered document hook action (used by document type hooks).

---

## Applications (Customer Applications) 🧭

- **GET `/api/customer-applications/`**
  - **Description:** List and search customer applications.

- **POST `/api/customer-applications/quick-create/`**
  - **Input:** JSON per `CustomerApplicationQuickCreateSerializer`
  - **Description:** Create a minimal application with associated workflows and documents.

- **POST `/api/customer-applications/<id>/advance-workflow/`**
  - **Description:** Mark current workflow step as completed and create the next step.

- **POST `/api/customer-applications/<id>/workflows/<workflow_id>/status/`**
  - **Input:** `{ "status": "pending|completed|..." }`
  - **Description:** Update a workflow step's status (validates document collection where needed).

- **POST `/api/customer-applications/<id>/reopen/`**, **POST `/api/customer-applications/<id>/force-close/`**
  - **Description:** Reopen a completed application or force-close (admin/permission checks apply).

---

## Invoices & Invoice Actions 💳

- **GET `/api/invoices/`**, **POST `/api/invoices/`**, **GET `/api/invoices/<id>/`**, **PATCH `/api/invoices/<id>/`**
  - **Description:** Standard CRUD for invoices (list supports `search`, `hide_paid` query params).

- **GET `/api/invoices/propose/?invoice_date=YYYY-MM-DD`**
  - **Description:** Propose the next invoice number for a given year/date.

- **GET `/api/invoices/get_customer_applications/<customer_id>/`**
  - **Description:** Find applications for a customer suitable for invoicing (supports filters for excluding incomplete, statuses, etc.).

- **GET `/api/invoices/get_invoice_application_due_amount/<invoice_application_id>/`**
  - **Description:** Get due/paid/amount for a specific invoice application entry.

- **GET `/api/invoices/<id>/download/?file_format=docx|pdf`**
  - **Description:** Generate and return the invoice document (DOCX or converted PDF).

- **POST `/api/invoices/<id>/download-async/`**
  - **Input:** `{ "file_format": "pdf" }` (optional)
  - **Description:** Queue invoice generation job and return job info with status/stream/download URLs.

- **GET `/api/invoices/download-async/status/<job_id>/`**, **GET `/api/invoices/download-async/stream/<job_id>/`**, **GET `/api/invoices/download-async/file/<job_id>/`**
  - **Description:** Status polling, SSE progress stream, and file download for async invoice generation jobs.

- **POST `/api/invoices/<id>/mark-as-paid/`**
  - **Input:** `{ "payment_type": string, "payment_date": "YYYY-MM-DD" }`
  - **Description:** Mark an invoice as paid; may create payments for associated invoice applications.

- **GET `/api/invoices/<id>/delete-preview/`**
  - **Permissions:** Superuser-only
  - **Description:** Preview impact of deleting an invoice (counts of related objects).

- **POST `/api/invoices/<id>/force-delete/`**, **POST `/api/invoices/bulk-delete/`**
  - **Permissions:** Superuser-only
  - **Description:** Force delete or bulk delete invoices (with options to also delete applications).

---

## Invoice Import (AI-powered) 🤖

- **GET `/api/invoices/import/config`**
  - **Description:** Returns LLM provider configuration, supported file formats, and defaults (`currentProvider`, `currentModel`, `maxWorkers`).

- **POST `/api/invoices/import/single`**
  - **Input (multipart/form-data):** `file` (required), `llm_provider` (optional), `llm_model` (optional)
  - **Description:** Import a single invoice file using AI parsing. Returns parsed data and possibly created `invoice` and `customer` references. Status codes vary (200 success, 409 duplicate, 400/500 on errors).

- **POST `/api/invoices/import/batch`**
  - **Input (multipart/form-data):** `files[]` (required), optional `paid_status[]`, `llm_provider`, `llm_model`
  - **Description:** Create a background job and return an SSE stream response for live updates. Each file is queued for processing; client can also poll or stream the job using the job id.

- **GET `/api/invoices/import/status/<job_id>`**
  - **Description:** Poll a batch import job status summary (processed/imported/duplicates/errors counts).

- **GET `/api/invoices/import/stream/<job_id>`**
  - **Description:** SSE stream for real-time updates (events: `start`, `file_start`, `parsing`, `file_success`, `file_duplicate`, `file_error`, `complete`).

---

## OCR & Document OCR 🧾🔎

- **POST `/api/ocr/check/`**
  - **Input:** `file` (required), `doc_type` (required), optional `use_ai`, `save_session`, `img_preview`, `resize`, `width`.
  - **Description:** Queue OCR job (MRZ/passport or other doc checks). Returns `job_id` and `status_url` to poll. Accepted file types: JPEG, PNG, TIFF, PDF.

- **GET `/api/ocr/status/<job_id>/`**
  - **Description:** Poll OCR job status and get `mrz_data` or errors when completed.

- **POST `/api/document-ocr/check/`**
  - **Input:** `file` (PDF/Excel/Word)
  - **Description:** Queue a general document OCR job (text extraction). Returns `job_id` and `status_url`.

- **GET `/api/document-ocr/status/<job_id>/`**
  - **Description:** Poll document OCR job status and get extracted `text` on completion.

---

## Payments 💸

- **GET `/api/payments/`**
  - **Query params:** `invoice_application_id` to filter payments for a specific invoice application.

- **POST `/api/payments/`**
  - **Input:** Payment payload (see `PaymentSerializer`), `invoice_application` is required.

---

## Admin & Server Tools ⚙️

- **GET `/api/backups/`**
  - **Description:** List available backup files and metadata. **Permissions:** Superuser-only.

- **GET `/api/backups/download/<filename>/`**
  - **Description:** Download a backup archive file. **Permissions:** Superuser-only.

- **POST `/api/backups/upload/`**
  - **Input:** multipart/form-data with `backup_file` field
  - **Description:** Upload a backup archive to the server. **Permissions:** Superuser-only.

- **DELETE `/api/backups/delete-all/`**
  - **Description:** Delete all backups from disk. **Permissions:** Superuser-only.

- **GET `/api/backups/start/`** (SSE)
  - **Query params:** `include_users` (0/1 or true/false)
  - **Description:** Start a backup process and stream progress via Server-Sent Events (SSE). **Permissions:** Superuser-only.

- **POST `/api/backups/restore/`** (SSE) — or legacy **GET** `/api/backups/restore/?file=<filename>`
  - **Query params:** `file` (required), `include_users` (optional)
  - **Description:** Restore a backup archive and stream progress via SSE. Can be invoked via HTTP POST (viewset action) or via legacy plain GET SSE view that accepts `file` as a query param. **Permissions:** Superuser-only.

- **GET `/api/server-management/`**
  - **Description:** Server management actions (superuser-only). Common actions include:
    - **POST `/api/server-management/clear-cache/`** — Clear application cache.
    - **GET `/api/server-management/media-diagnostic/`** — Run media files diagnostic.
    - **POST `/api/server-management/media-repair/`** — Repair media file paths.

- **GET `/api/dashboard-stats/`**
  - **Description:** Basic dashboard stats (legacy/simple endpoint used by older frontends). Requires authentication.

---

## Workflow Utilities & Cron

- **GET `/api/compute/doc_workflow_due_date/<task_id>/<start_date>/`**
  - **Description:** Compute workflow due date for a task and start date.

- **GET `/api/cron/exec_cron_jobs/`**
  - **Description:** Trigger Huey cron job tasks (`run_full_backup_now`, `run_clear_cache_now`). Returns a queued status.

---

## Notes & Authentication

- Most endpoints require authentication (JWT or session). Some admin actions are restricted to superusers or users with specific permissions.
- File uploads use multipart/form-data. For precise request/response schemas, consult the OpenAPI schema at `/api/schema/` or the browsable API.

---

**For further details and the most current endpoint list, visit the `api/urls.py` and `api/views.py` files or the running OpenAPI schema at** `/api/schema/`.
