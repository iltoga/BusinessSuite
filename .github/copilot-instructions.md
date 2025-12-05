# AI Coding Assistant Instructions for RevisBaliCRM

## Project Overview

RevisBaliCRM is a Django-based ERP/CRM system for service agencies, managing customer applications with document workflows, invoicing, and payments. Key components include customer applications, document processing with OCR, task-based workflows, and REST API integration.

## Architecture

- **Apps**: `customers`, `products`, `customer_applications`, `invoices`, `payments`, `core`
- **Data Flow**: Products define tasks/workflows and document types → CustomerApplications link customers to products → Documents collected per application → Workflows track task progress → Invoices generated from completed applications
- **Key Models**:
  - `DocApplication`: Core application entity with status tracking
  - `Document`: File/number/expiration/details with completion logic based on `DocumentType` requirements
  - `DocWorkflow`: Task progress with due dates and notifications
  - `Product`: Defines tasks and required document types
- **UI**: Django templates + Bootstrap + Django Unicorn for reactive components (e.g., dynamic form updates without full page reloads)

## Critical Workflows

- **Setup**: Run `./start.sh` for migrations, data population, user creation, static collection
- **Data Population**: Use `fixtures.sh` or management commands like `populate_documenttypes`, `populate_products`
- **Reset**: `./reset_app.sh` clears DB and migrations for clean slate
- **Deployment**: Docker Compose with Postgres, pgAdmin, memcached, cron jobs
- **Backups**: Automated to Dropbox via `django-dbbackup`
- **OCR Processing**: Uses `pytesseract` and `passporteye` for passport scans, stores metadata in `Document.metadata` JSONField

## Project Conventions

- **APIs**: Django REST Framework (DRF) with APIView classes for endpoints; token authentication via `rest_framework.authtoken`; serializers in `api/serializers/`
- **Views**: Django generic class-based views (ListView, CreateView, etc.) with templates; Bootstrap 5 for styling; Django Unicorn for reactive components (AJAX updates via `unicorn:click`, `unicorn:model`)
- **Forms**: Django ModelForm and inlineformset_factory for formsets; rendered with Crispy Forms (`{% load crispy_forms_tags %}`, `{{ form | crispy }}`); Widget Tweaks for field customization; Nested Admin for inline forms in admin
- **Document Completion**: In `Document.save()`, check fields based on `DocumentType` flags (e.g., `has_file`, `has_expiration_date`)
- **Upload Paths**: `documents/<customer_folder>/<application_id>/<filename>` via `get_upload_to()` function
- **Workflow Progression**: Applications advance via `DocWorkflow` completion; due dates calculated with business day logic
- **Search Managers**: Custom managers like `DocApplicationManager.search_doc_applications()` for query filtering
- **Signals**: Post-delete cleanup for application folders using `shutil.rmtree()`
- **Environment**: Use `.env` for secrets; settings split into `base.py`, `dev.py`, `prod.py`
- **API**: DRF with token auth; endpoints for customers, products, OCR checks
- **Cron Jobs**: Disabled Django cron due to Django 5 compatibility; use custom scripts

## Examples

- **Creating a Document**: Ensure `completed` field updates based on `doc_type.has_file` etc. in `save()` method
- **Workflow Due Dates**: Use `calculate_due_date()` from `core.utils.dateutils` for business day calculations
- **Model Deletion**: Override `delete()` to check relations (e.g., prevent deleting invoiced applications)
- **File Handling**: Use `default_storage` for cloud/local storage abstraction
- **Unicorn Components**: Place in app `components/` folders for reactive UI elements

## Integration Points

- **Dropbox**: File storage and backups via `django-storages`
- **OCR**: `passporteye` for MRZ reading; metadata extraction stored as JSON
- **Payments**: Custom payment processing (check `payments` app)
- **External APIs**: REST endpoints for third-party integrations

Focus on maintaining data integrity, especially around document completion and workflow states. Use existing patterns for new features to ensure consistency.
When possible use context7 mcp server to get updated information about the python packages and libraries used in the project.
