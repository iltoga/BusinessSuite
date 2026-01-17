# GitHub Copilot Project Instructions — RevisBaliCRM

## Project context

RevisBaliCRM is a Django-based ERP/CRM for service agencies. It manages customer applications, document workflows (with OCR), tasks, invoicing, and payments.

## Architecture & conventions

- Apps: `customers`, `products`, `customer_applications`, `invoices`, `payments`, `core`.
- Data flow: Products → required document types/tasks → CustomerApplications → Documents → Workflows → Invoices.
- UI: Django templates + Bootstrap 5 + Django Unicorn for reactive UI.
- API: DRF `APIView` classes, token auth (`rest_framework.authtoken`), serializers in `api/serializers/`.
- Forms: Django `ModelForm` + `inlineformset_factory`, render with Crispy Forms and Widget Tweaks.

## Code quality rules (backend)

- Keep views thin; place business logic in models/services/managers.
- Preserve public APIs and existing patterns; avoid breaking changes.
- Model changes must include migrations and any needed admin/form/serializer updates.
- Maintain data integrity for:
  - `Document.completed` logic in `Document.save()` based on `DocumentType` flags.
  - Workflow progression via `DocWorkflow` and due dates using `calculate_due_date()`.
  - Safe deletion checks (e.g., prevent deleting invoiced applications).
- Use `default_storage` for file access and `get_upload_to()` for upload paths.
- Keep settings/secrets in `.env`; do not hardcode credentials.

## Code quality rules (frontend/templates)

- Use Bootstrap 5 classes and existing template blocks; avoid ad‑hoc styling.
- Keep templates consistent with current layout and include `{% load crispy_forms_tags %}` when rendering forms.
- Prefer Django Unicorn components (`components/` folders) for interactive behavior; minimize custom JS.

## Style & consistency

- Python: follow PEP 8, use clear naming, add type hints when obvious.
- Avoid unused imports; keep modules small and single‑responsibility.
- Do not reformat unrelated code; keep diffs minimal.

## Tests & validation

- Update or add tests in the relevant app’s `tests/` when changing behavior.
- For API changes, add/adjust DRF tests and serializers.
- Keep fixtures aligned with `fixtures/` when adding core data types.

## When adding features

- Update URLs, views, serializers, permissions, and templates consistently.
- Ensure admin, forms, and API serializers reflect model changes.
- Use existing custom managers (e.g., `DocApplicationManager.search_doc_applications()`) for search logic.

## Documentation & references

- Use the Context7 documentation source when clarifying library behavior.
- Keep README/API docs aligned if endpoints or workflows change.
