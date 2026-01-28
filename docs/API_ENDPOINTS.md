# API Endpoints Documentation

This document lists the main API endpoints exposed by the application in this repository, including their payload (input parameters/files) and a short description for each.

> **Note:** This list is based on code search and may be incomplete. For a complete and up-to-date list, please consult the [api/urls.py file on GitHub](https://github.com/iltoga/BusinessSuite/blob/main/api/urls.py) or the browsable API documentation provided by the application.

---

## Authentication

- **POST `/api/api-token-auth/`**
  - **Input:** `{ "username": string, "password": string }`
  - **Description:** Obtain an authentication token for API access.

- **GET `/api/session-auth/`**
  - **Input:** Session credentials (via browser or API client)
  - **Description:** Session-based authentication provided by Django REST Framework.

---

## Customers

- **GET `/api/customers/`**
  - **Input:** None
  - **Description:** Retrieve a list of all customers. Returns a list of customer objects including fields such as `first_name`, `last_name`, `company_name`, `email`, `telephone`, `passport_number`, `passport_expiration_date`, `birthdate`, and `birth_place`.

- **GET `/api/customers/search/?q=<query>`**
  - **Input:** Query parameter `q` (string to search by first name, last name, or email)
  - **Description:** Search for customers by name or email.

---

## Products

- **GET `/api/products/`**
  - **Input:** None
  - **Description:** Retrieve a list of all products.

- **GET `/api/products/get_product_by_id/<product_id>/`**
  - **Input:** URL parameter `product_id` (integer)
  - **Description:** Retrieve a product by ID, including its required and optional documents. Calls return a JSON object with keys: `product` (the product data), `required_documents` (list), and `optional_documents` (list).

- **GET `/api/products/get_products_by_product_type/<product_type>/`**
  - **Input:** URL parameter `product_type` (string)
  - **Description:** Retrieve products filtered by product type.

---

## Invoices & Applications

- **GET `/api/invoices/get_customer_applications/<customer_id>/`**
  - **Input:** URL parameter `customer_id` (integer)
  - **Description:** Retrieve all applications for a particular customer, annotated with the count of related invoice applications.

---

## OCR

- **POST `/api/ocr/check/`**
  - **Input:** Multipart/form-data:
    - `file`: File (required, image or PDF)
    - `doc_type`: String (required, document type)
    - `save_session`: Boolean (optional, if true, stores file path and MRZ data in session)
    - `img_preview`: Boolean (optional, if true, returns a base64-encoded resized image)
    - `resize`: Boolean (optional, if true, resizes image)
    - `width`: Integer (optional, width for resizing)
  - **Description:** Queue OCR (Optical Character Recognition) check, e.g., for passport MRZ extraction. Returns a `job_id` and `status_url` for polling.
  - **Validation:** Only JPEG, PNG, TIFF, and PDF files are accepted. Both `file` and `doc_type` are required.

- **GET `/api/ocr/status/<job_id>/`**
  - **Input:** URL parameter `job_id` (UUID)
  - **Description:** Poll OCR job status. Returns `status`, `progress`, and when completed, the same payload as the original OCR response (`mrz_data`, optional `b64_resized_image`, `ai_warning`).

---

## Workflow and Utilities

- **GET `/api/compute/doc_workflow_due_date/<task_id>/<start_date>/`**
  - **Input:** URL parameters:
    - `task_id`: Integer (task to compute due date for)
    - `start_date`: String (date in supported format)
  - **Description:** Compute the due date for a document workflow step based on a start date.

- **POST `/api/cron/exec_cron_jobs/`**
  - **Input:** None
  - **Description:** Trigger execution of scheduled cron jobs (background maintenance or automation tasks).

---

## Additional Notes

- All endpoints generally require authentication via token or session unless otherwise configured.
- For endpoints that accept or return files (OCR, document upload), refer to the application’s browsable API or OpenAPI schema for exact payload formats.
- The API is designed for use with Django REST Framework and supports JSON, form, and multipart payloads.

---

**For further details and the most current endpoint list, visit the [`api/urls.py` file](https://github.com/iltoga/BusinessSuite/blob/main/api/urls.py).**
