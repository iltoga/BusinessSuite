# Create Document Type Hook — Copilot Prompt

Purpose

- Assist a developer to generate a new Document Type Hook for RevisBaliCRM.

- Follow the existing hooks architecture and patterns: the hook registry, lifecycle signal dispatch, UI actions, and tests.

Project Context

- This repository uses a pluggable document-type hook system under customer_applications/hooks.

- Use the project's existing codebase in customer_applications/hooks and related files to generate the hook; review these files when producing code:

  - `customer_applications/hooks/base.py` (BaseDocumentTypeHook, DocumentAction)

  - `customer_applications/hooks/registry.py` (HookRegistry and global `hook_registry`)

  - `customer_applications/hooks/signals.py` (signal dispatch to hooks)

  - Example hooks: `ktp_sponsor.py` and `surat_permohonan.py` in customer_applications/hooks/

  - `customer_applications/views/document_action_view.py` (backend execute_action endpoint)

  - `customer_applications/templates/customer_applications/partials/document_actions.html` and `business_suite/static/js/document_actions.js` (UI integration)

- The primary classes and files involved are those listed above.
Goals for generated hook

- Create a single, focused Python file implementing a hook class subclassing `BaseDocumentTypeHook`.

- The class must set `document_type_name` to match the `DocumentType.name` in the database.

- Implement at least one hook lifecycle method: `on_init`, `on_pre_save`, `on_post_save`, `on_pre_delete`.

- Optionally add extra UI actions via `get_extra_actions()` and an action handler `execute_action()`.

- Register the hook in `customer_applications/hooks/__init__.py` using `hook_registry.register(YourHook())`.

- Offer safe, testable examples for common tasks: default-file assignment, auto-generating a document, or updating related workflows.

Coding Conventions and Safeguards

- Import `TYPE_CHECKING` from typing; local import models inside functions to avoid circular imports.

- For logging use module-level `logger = logging.getLogger(__name__)`.

- Use Django `settings` and `default_storage` when dealing with files; always check `default_storage.exists()` before opening.

- Use `document.file.save(filename, File(file_obj), save=False)` when called from `on_pre_save` to avoid re-saving in the middle of save.

- If your code modifies `document` outside `pre_save` (e.g. in an action or `post_save`), use `document.save()` with care to avoid infinite loops.

- Wrap IO and network operations in try/except and log exceptions with appropriate log level.

- If an action needs to modify the Document and update UI state, return `{'success': True, 'message': '...'};` on error, use `{'success': False, 'error': '...'};`.

- Use `request.user` where relevant for permission checks in `execute_action`.

Action Integration & UI

- If implementing UI actions, create `DocumentAction` instances in `get_extra_actions()`:

  - `DocumentAction(name='auto_generate', label='Auto Generate', icon='fas fa-magic', css_class='btn-success')`

- Implement `execute_action(self, action_name, document, request) -> dict` to handle action(s), returning success/error.

- The DocumentUpdateForm loads `extra_actions` using hook_registry in `_load_extra_actions()`; the template includes the JS file `static/js/document_actions.js` which calls the endpoint at

  - `/customer_applications/api/documents/<document_id>/actions/<action_name>/` (use reverse URL `document-action`).

Testing

- Add unit tests for the hook logic (business logic of the hook): test default-file assignment, correct setting of metadata, or generated file existence.
- Add integration tests to verify DocumentActionView triggers the hook action and the document is updated as expected.
- For registry and lifecycle tests, follow existing property tests: register test hooks with HookRegistry (clear it in setUp) and verify they are called by signals on `post_init`, `pre_save`, `post_save`, `pre_delete`.
- Use `assert` to check the proper `DocumentAction` is returned and `execute_action()` returns expected dict structure.

Example 1: Default file assignment (pre_save)

- Typical use-case: If the document has no file uploaded by user and a repo-wide default file exists, assign it.

- Schematic Implementation:

  ```py
  import logging
  from typing import TYPE_CHECKING
  from django.conf import settings
  from django.core.files import File
  from django.core.files.storage import default_storage
  from customer_applications.hooks.base import BaseDocumentTypeHook

  if TYPE_CHECKING:
      from customer_applications.models import Document

  logger = logging.getLogger(__name__)

  class ExampleDefaultFileHook(BaseDocumentTypeHook):
      document_type_name = "My Default File Document"

      def on_pre_save(self, document: 'Document', created: bool):
          # If user uploaded a file, use it
          if document.file and document.file.name:
              return

          default_path = getattr(settings, 'DEFAULT_MY_DOC_FILE', None)
          if not default_path:
              return

          if not default_storage.exists(default_path):
              logger.warning('Default file configured but not found: %s', default_path)
              return

          try:
              with default_storage.open(default_path, 'rb') as f:
                  filename = default_path.split('/')[-1]
                  document.file.save(filename, File(f), save=False)
          except Exception as e:
              logger.error('Failed to assign default file: %s', str(e))
  ```

- Register the hook in `customer_applications/hooks/__init__.py`:

  ```py
  from .example_default import ExampleDefaultFileHook
  hook_registry.register(ExampleDefaultFileHook())
  ```

Example 2: Add UI action that auto-generates a document (like `SuratPermohonanHook`)

- Pattern: `get_extra_actions()` returns a list of DocumentAction(s); `execute_action()` handles the action, uses a service to create a file in memory (BytesIO), and `document.file.save(, ContentFile(...), save=True)` to persist it.
- Schematic Implementation:

  ```py
  from django.core.files.base import ContentFile
  from customer_applications.hooks.base import BaseDocumentTypeHook, DocumentAction
  from django.conf import settings
  import logging
  logger = logging.getLogger(__name__)

  class ExampleGenerateHook(BaseDocumentTypeHook):
      document_type_name = "Example Generated Doc"

      def get_extra_actions(self):
          return [DocumentAction(name='generate', label='Generate', icon='fas fa-magic', css_class='btn-success')]

      def execute_action(self, action_name, document, request):
          if action_name != 'generate':
              return {'success': False, 'error': 'Unknown action'}
          try:
              # Avoid circular imports at module level
              from letters.services.LetterService import LetterService

              # Call your generation service using template and data
              template_name = getattr(settings, 'MY_TEMPLATE', 'my_template.docx')
              service = LetterService(document.doc_application.customer, template_name)
              data = service.generate_letter_data()
              doc_buffer = service.generate_letter_document(data)
              filename = f"generated_doc_{document.doc_application.customer.pk}.docx"
              document.file.save(filename, ContentFile(doc_buffer.getvalue()), save=True)
              return {'success': True, 'message': 'Document generated successfully'}
          except FileNotFoundError as e:
              logger.error('Template not found: %s', e)
              return {'success': False, 'error': f'Template not found: {e}'}
          except Exception as e:
              logger.error('Failed to generate doc: %s', e)
              return {'success': False, 'error': str(e)}
  ```

Best Practices Checklist

- Name: use a clear `document_type_name`; it must match `DocumentType.name` in the DB.
- Avoid circular imports: import models inside functions or use `TYPE_CHECKING`/`if TYPE_CHECKING:` pattern.
- Use `save=False` inside `pre_save` and only call `document.save()` when safe (like in actions).
- Use `default_storage` with `exists` checks and `open` in a `with` block.
- Use structured logging; log at `info`, `warning`, or `error` appropriately.
- Keep actions idempotent and re-runnable: e.g., if generating an invoice file, don't create multiple invoices when same action triggers twice unless intended.
- Handle default settings gracefully and document new settings needed in README or `settings/base.py`.
- Register the hook in `customer_applications/hooks/__init__.py` to make it available at startup.
- Add tests: unit tests, view tests for `DocumentActionView`, and property tests for lifecycle invocation.

Testing/CI Notes

- Add tests under `customer_applications/tests/` or `customer_applications/tests/hooks/`.
- Reuse the `TrackingHook` pattern in `customer_applications/tests/test_hook_registry_properties.py` to ensure signals call your hook.
- For action tests, use Django `Client` and `Document` fixtures; call the post action URL and assert JSON response and file existence or metadata.

Final Checklist — PR Guidance

- Add the new hook file: `customer_applications/hooks/<your_hook>.py`.

- Add an import and registration entry to `customer_applications/hooks/__init__.py`.

- Expose default settings if needed in `business_suite/settings/base.py` and document them.

- Add tests for lifecycle and action behavior and register in CI.

- Include usage docs: Add one section to repo README or docs describing the hook, example use-cases, and settings.

Deliverable

- One markdown prompt file including the above instructions, code snippets, and checklists.

When generating code, ensure it fits the project's style and use existing patterns from `ktp_sponsor.py` and `surat_permohonan.py`. The prompt should produce minimal, well-scoped classes with thorough testing and documentation.
