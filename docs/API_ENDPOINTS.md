# API Endpoints Documentation

This file summarizes the main API surface in `backend/api/urls.py` and related DRF viewsets.

> For exact request/response schemas, always verify against:
>
> - OpenAPI: `/api/schema/`
> - Swagger: `/api/schema/swagger-ui/`

---

## Authentication

- `POST /api/api-token-auth/` — obtain JWT pair via custom token view
- `GET /api/session-auth/` — DRF session auth endpoints
- `GET /api/mock-auth-config/` — mock auth claims/config (dev/testing mode)

---

## Users & Settings

- `GET /api/user-profile/me/`
- `PATCH /api/user-profile/update_profile/`
- `POST /api/user-profile/upload_avatar/` (multipart)
- `POST /api/user-profile/change_password/`
- `POST /api/user-profile/logout/`

- `GET /api/user-settings/me/`
- `PATCH /api/user-settings/me/`

---

## Reference Data

- `GET /api/country-codes/`
- `GET /api/holidays/`, `POST /api/holidays/`, `PATCH /api/holidays/{id}/`, `DELETE /api/holidays/{id}/`

---

## Customers

- `GET /api/customers/`
- `POST /api/customers/`
- `GET /api/customers/{id}/`
- `PATCH /api/customers/{id}/`
- `DELETE /api/customers/{id}/`
- `GET /api/customers/search/?q=...`
- `POST /api/customers/{id}/toggle-active/`
- `GET /api/customers/{id}/uninvoiced-applications/`
- `GET /api/customers/{id}/applications-history/`
- `POST /api/customers/bulk-delete/` (superuser)
- `POST /api/customers/quick-create/`

### Passport check flow (async)

- `POST /api/customers/check-passport/` (multipart)
  - Queues Huey task and returns `job_id`
- Progress/result is consumed via async-job/SSE status endpoints.

---

## Products

- `GET /api/products/`
- `POST /api/products/`
- `GET /api/products/{id}/`
- `PATCH /api/products/{id}/`
- `DELETE /api/products/{id}/`
- `GET /api/products/get_product_by_id/{product_id}/`
- `GET /api/products/get_products_by_product_type/{product_type}/`
- `GET /api/products/{id}/can-delete/`
- `POST /api/products/bulk-delete/` (superuser)
- `POST /api/products/quick-create/`

### Product import/export (async)

- `POST /api/products/export/start/`
- `GET /api/products/export/download/{job_id}/`
- `POST /api/products/import/start/` (multipart)

---

## Document types

- `GET /api/document-types/`
- `POST /api/document-types/`
- `PATCH /api/document-types/{id}/`
- `DELETE /api/document-types/{id}/`
- `GET /api/document-types/{id}/can-delete/`
- `GET /api/document-types/{id}/deprecation-impact/`

---

## Customer applications

- `GET /api/customer-applications/`
- `POST /api/customer-applications/`
- `GET /api/customer-applications/{id}/`
- `PATCH /api/customer-applications/{id}/`
- `DELETE /api/customer-applications/{id}/`
- `POST /api/customer-applications/bulk-delete/` (superuser)
- `POST /api/customer-applications/quick-create/`
- `POST /api/customer-applications/{id}/advance-workflow/`
- `POST /api/customer-applications/{id}/reopen/`
- `POST /api/customer-applications/{id}/force-close/`
- `POST /api/customer-applications/{id}/workflows/{workflow_id}/status/`
- `POST /api/customer-applications/{id}/workflows/{workflow_id}/due-date/`
- `POST /api/customer-applications/{id}/workflows/{workflow_id}/rollback/`

### Calendar sync behavior note

Application create/update/workflow transitions queue `sync_application_calendar_task` (Huey), which:

1. updates local `CalendarEvent` rows,
2. triggers Google Calendar sync via calendar-event model signals.

---

## Documents

- `GET /api/documents/`
- `POST /api/documents/`
- `PATCH /api/documents/{id}/`
- `GET /api/documents/{id}/download/`
- `GET /api/documents/{id}/print/`
- `POST /api/documents/merge-pdf/`
- `POST /api/documents/{id}/actions/{action_name}/`

### Categorization / validation helpers

- `POST /api/customer-applications/{application_id}/categorize-documents/`
- `POST /api/customer-applications/{application_id}/categorize-documents/init/`
- `POST /api/document-categorization/{job_id}/upload/`
- `GET /api/document-categorization/stream/{job_id}/` (SSE)
- `POST /api/document-categorization/{job_id}/apply/`
- `GET /api/document-categorization/{job_id}/status/`
- `POST /api/documents/{document_id}/validate-category/`
- `GET /api/documents/{document_id}/validation-stream/` (SSE)

---

## Invoices

- `GET /api/invoices/`
- `POST /api/invoices/`
- `GET /api/invoices/{id}/`
- `PATCH /api/invoices/{id}/`
- `GET /api/invoices/propose/?invoice_date=YYYY-MM-DD`
- `GET /api/invoices/get_customer_applications/{customer_id}/`
- `GET /api/invoices/get_invoice_application_due_amount/{invoice_application_id}/`
- `GET /api/invoices/{id}/download/?file_format=docx|pdf`
- `POST /api/invoices/{id}/download-async/`
- `GET /api/invoices/download-async/status/{job_id}/`
- `GET /api/invoices/download-async/stream/{job_id}/` (SSE)
- `GET /api/invoices/download-async/file/{job_id}/`
- `POST /api/invoices/{id}/mark-as-paid/`
- `GET /api/invoices/{id}/delete-preview/` (superuser)
- `POST /api/invoices/{id}/force-delete/` (superuser)
- `POST /api/invoices/bulk-delete/` (superuser)

### Invoice import

- `GET /api/invoices/import/config`
- `POST /api/invoices/import/single` (multipart)
- `POST /api/invoices/import/batch` (multipart)
- `GET /api/invoices/import/status/{job_id}`
- `GET /api/invoices/import/stream/{job_id}` (SSE)

---

## Payments

- `GET /api/payments/`
- `POST /api/payments/`
- `GET /api/payments/{id}/`
- `PATCH /api/payments/{id}/`
- `DELETE /api/payments/{id}/`

> On payment create/update/delete, invoice-application and invoice statuses are recalculated.

---

## OCR

- `POST /api/ocr/check/`
- `GET /api/ocr/status/{job_id}/`
- `POST /api/document-ocr/check/`
- `GET /api/document-ocr/status/{job_id}/`

---

## Calendar, reminders, notifications

- `GET /api/calendar/` (+ sync actions in viewset)
- `GET /api/tasks/` (+ sync actions in viewset)
- `GET /api/calendar-reminders/`
- `POST /api/calendar-reminders/`
- `GET /api/calendar-reminders/stream/` (SSE)
- `GET /api/workflow-notifications/`
- `POST /api/workflow-notifications/{id}/resend/`
- `POST /api/workflow-notifications/{id}/cancel/`
- `GET /api/workflow-notifications/stream/` (SSE)

Push/webhook:

- `POST /api/push-notifications/register/`
- `POST /api/push-notifications/unregister/`
- `POST /api/push-notifications/test/`
- `POST /api/push-notifications/send-test/` (admin/staff)
- `POST /api/push-notifications/send-test-whatsapp/` (admin/staff)
- `GET|POST /api/notifications/whatsapp/webhook/`

---

## Reports

- `GET /api/reports/`
- `GET /api/reports/revenue/`
- `GET /api/reports/kpi-dashboard/`
- `GET /api/reports/invoice-status/`
- `GET /api/reports/monthly-invoices/`
- `GET /api/reports/cash-flow/`
- `GET /api/reports/customer-ltv/`
- `GET /api/reports/application-pipeline/`
- `GET /api/reports/product-revenue/`
- `GET /api/reports/product-demand/`
- `GET /api/reports/ai-costing/`

---

## Admin tools & system

- `GET /api/backups/`
- `GET /api/backups/download/{filename}/`
- `POST /api/backups/upload/`
- `DELETE /api/backups/delete-all/`
- `GET /api/backups/start/` (SSE)
- `POST /api/backups/restore/` (SSE)
- `GET /api/server-management/` (+ action endpoints)
- `GET /api/dashboard-stats/`
- `GET /api/async-jobs/`
- `GET /api/async-jobs/status/{job_id}/` (SSE)
- `GET|POST /api/cron/exec_cron_jobs/`
- `GET /api/app-config/`

---

## Notes

- Most endpoints require authentication.
- Some actions are superuser-only or staff/admin-group restricted.
- Many heavy operations are asynchronous and should be tracked via job status/SSE endpoints.
