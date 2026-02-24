# Implementation Feedback Log

## Progress Log

- **2026-02-13:** Calendar integration refactor completed (local `CalendarEvent` mirror model, signal-driven Huey sync, Google Calendar API adjustments, workflow transition-on-done behavior, docs updated for new flow)
- **2026-02-13:** Documentation alignment pass completed for `/.github/copilot-instructions.md` and `/docs/*`
- **2026-02-02:** Completed Phase 11 - Integration & Finalization (feature flagging via `DISABLE_DJANGO_VIEWS`, CSP nonce middleware/tests, Playwright + axe accessibility coverage)
- **2026-01-24:** Completed Phase 0 - Foundation setup
- **2026-01-24:** Added shared docs registry and custom API exception handler
- **2026-01-24:** Initialized ZardUI and added shared DataTable/ConfirmDialog components
- **2026-01-24:** Added auth/main layouts and GlobalToastService
- **2026-01-24:** Implemented Customer List feature with search, pagination, and status toggling
- **2026-01-25:** Added Application Detail view with OCR polling and shared FileUpload component
- **2026-01-26:** Implemented Products management (list/detail/form), API CRUD for products, and SortableMultiSelect component
- **2026-01-28:** Added CustomerSelect shared component and workflow progression UI for applications
- **2026-01-29:** Implemented Letters (Surat Permohonan) API + Angular form with customer auto-fill
- **2026-01-29:** Implemented Invoices & Payments API + Angular list/detail/form with payment modal
- **2026-01-30:** Added JWT auth claims (roles/groups/is_superuser) and Angular admin-gated delete actions with bulk delete dialogs

## Reuse Hints

- Reuse calendar mirror flow (`CalendarEvent` + async sync tasks) for any new calendar-producing domain logic.
- Prefer existing shared selectors/dialogs/upload/table components before introducing new ones.
- Keep API contract-first workflow: serializer change -> schema generation -> frontend client generation.

## Refactor Requests

- None currently open.

## Technical Debt

- Continue consolidating any remaining legacy direct Google API calls toward local mirror + queue-based sync where applicable.

## Wins & Lessons Learned

- Local calendar mirror with async sync reduces request-path coupling to Google API availability.
- Signal + task architecture keeps DB writes transactional while preserving external sync reliability.
- Explicit docs updates immediately after refactors reduce drift for future feature work.

## Fixes

- **2026-02-24: AI Document Categorization — Model Findings**
  - `openai/gpt-5-nano` via Azure/OpenRouter does **not** support vision + structured JSON output. All files fail with "No JSON object found".
  - `google/gemini-2.5-flash-lite` works excellently: 8/8 test files correctly categorized, avg confidence 93.8%, ~3.8s/file sequential, ~6s wall-clock parallel for 8 files.
  - PDFs must be converted to JPEG images before sending to vision APIs (OpenAI rejects `application/pdf` as `image_url` MIME type). Used `pdf2image` for conversion.
  - Default model for production should be `google/gemini-2.5-flash-lite`.

- **2026-02-09: OpenAPI Schema & Build Integrity Fix**
  - Added serializer fallbacks for ViewSets used with `@extend_schema`.
  - Improved schema generation reliability and frontend build stability.

- **2026-02-01: Full Backup restore fix**
  - Resolved duplicate key issues on `django_content_type` during full restore.
  - Improved fixture resilience with natural keys.
