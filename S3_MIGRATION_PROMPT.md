# S3 Migration & Storage Abstraction Refactor

**Role:** Senior Django & DevOps Architect
**Task:** Refactor Django file handling for "Storage Abstraction", implement Cloudflare R2 (S3) support, and provide migration tools.

**Objective:**
We are migrating from local `FileSystemStorage` to Cloudflare R2 (S3).
**CRITICAL:** You must refactor the codebase to introduce a **Storage Abstraction Layer**. The application must be able to switch between Local Storage (HDD) and Cloud Storage (S3) simply by changing an environment variable (`USE_CLOUD_STORAGE=True/False`), without requiring ANY further code changes.

**Requirements:**

1. **Frontend & API Strategy (Direct S3 Loading):**
   - **Goal:** The Angular frontend (SSR/SPA) must load files/images directly from S3, NOT via a Django proxy view.
   - **Mechanism:** Django serializers must return the full, absolute URL to the file.
     - If `USE_CLOUD_STORAGE=True`: The URL must be a **Presigned URL** (for private files) or a public R2 URL, generated automatically by `django-storages`.
     - If `USE_CLOUD_STORAGE=False`: It returns the standard `/media/...` path (served by Nginx/Django).
   - **Configuration:** You must configure `django-storages` to sign URLs (`AWS_QUERYSTRING_AUTH = True`) so that private files (passports, invoices) are accessible to the frontend for a limited time (e.g., 1 hour) without making the bucket public.

2. **Storage Utility (`backend/core/utils/storage_helpers.py`):**
   - **Problem:** Background tasks (PgQueuer) and OCR tools (Tesseract, PDF conversion) currently rely on `default_storage.path(file_name)`, which crashes on S3.
   - **Solution:** Implement a Context Manager named `get_local_file_path(file_reference)`.
     - **Logic:**
       - If storage is Local: Yield `file_reference.path`.
       - If storage is Remote (S3): Download the file to a `NamedTemporaryFile`, yield the temp path, and delete it upon exit.
   - **Benefit:** Tools like Tesseract get the physical path they need, regardless of where the file actually lives.

3. **Refactor Existing Code:**
   - Scan `backend/` for all usages of `.path`.
   - **Target Files:**
     - `backend/core/tasks/ocr.py`
     - `backend/core/utils/passport_ocr.py`
     - `backend/core/utils/imgutils.py`
     - `backend/api/views.py` (check for manual `open()` calls).
   - Replace direct `.path` usage with your new `get_local_file_path` context manager.
   - Replace `open(path)` with `default_storage.open(name)` where streaming is sufficient.

4. **Data Migration Command (`migrate_files_to_s3`):**
   - Create a Django management command: `backend/core/management/commands/migrate_files_to_s3.py`.
   - **Functionality:**
     1. Iterate through all models with `FileField` or `ImageField` (use `django.apps.apps.get_models()`).
     2. For each file:
        - Check if it exists locally.
        - Upload it to the configured S3 bucket (using `default_storage.save` or `boto3` directly if needed to preserve names).
        - **Crucial:** Do NOT change the DB field value (the relative path string like `passports/abc.pdf` stays the same). Just ensure the file exists at that key in S3.
     3. Provide a `--dry-run` option.
   - **Buckets:** We have `crmrevisbalidev` (dev/test) and `crmrevisbali` (prod). The command should use the bucket defined in `settings.AWS_STORAGE_BUCKET_NAME`.

5. **DB Backup/Restore Refactoring:**
   - Currently, backups might use Dropbox or local storage.
   - **Task:** Refactor `backend/business_suite/settings/prod.py` (and `base.py` if relevant) to ensure `django-dbbackup` uses the **same S3 storage** defined in `STORAGES` for its backups.
   - Configure `DBBACKUP_STORAGE = 'storages.backends.s3boto3.S3Boto3Storage'` (or a custom subclass pointing to a `backups/` folder in the bucket) when `USE_CLOUD_STORAGE=True`.

6. **Settings & Configuration (`backend/business_suite/settings/prod.py`):**
   - Install `django-storages[boto3]`.
   - Define `USE_CLOUD_STORAGE = os.getenv('USE_CLOUD_STORAGE') == 'True'`.
   - **If True:**
     - `STORAGES["default"]` = `storages.backends.s3boto3.S3Boto3Storage`.
     - `AWS_ACCESS_KEY_ID`, `AWS_SECRET_ACCESS_KEY`.
     - `AWS_STORAGE_BUCKET_NAME` (Load from env; defaults to `crmrevisbalidev` in dev, `crmrevisbali` in prod).
     - `AWS_S3_ENDPOINT_URL` (Cloudflare R2 endpoint).
     - `AWS_S3_SIGNATURE_VERSION = 's3v4'`.
     - `AWS_QUERYSTRING_AUTH = True`.
   - **If False:**
     - Fallback to `django.core.files.storage.FileSystemStorage`.

7. **Output:**
   - Code for `core/utils/storage_helpers.py`.
   - Refactored code for the Task/Utility files.
   - The `migrate_files_to_s3` management command.
   - Updated `settings/prod.py` (Storage + DB Backup).
     -pdated `.env.example`.
