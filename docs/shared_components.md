# Shared Components Registry

This is the canonical registry for reusable Angular components.

Rules:

- Check this file before creating new UI components.
- Prefer extending existing shared components over creating duplicates.
- Update this registry in the same PR when adding/reworking shared components.
- When adding a new shared component, include:
  - selector
  - path
  - intended use
  - whether it is generic or domain-specific
- All new shared components must be documented here to ensure discoverability and consistency across the app.
- All new shared components should extend existing (zadrUI) primitives where possible, rather than creating new low-level UI elements.
- NEVER update zadrUI primitives. Only compose/extend them in this directory for app-specific shared components.

Base path: `frontend/src/app/shared/components/`

## Feature-level shared components

| Component               | Selector                        | Path                                         | Notes                                                                |
| ----------------------- | ------------------------------- | -------------------------------------------- | -------------------------------------------------------------------- |
| DataTable               | `app-data-table`                | `data-table/`                                | Generic tabular list rendering with column config and sorting hooks. |
| SearchToolbar           | `app-search-toolbar`            | `search-toolbar/`                            | Shared query/submit/search interaction.                              |
| PaginationControls      | `app-pagination-controls`       | `pagination-controls/`                       | Reusable page navigation controls.                                   |
| ConfirmDialog           | `app-confirm-dialog`            | `confirm-dialog/`                            | Generic confirmation dialog.                                         |
| BulkDeleteDialog        | `app-bulk-delete-dialog`        | `bulk-delete-dialog/`                        | Bulk-delete confirmation with payload/result contract.               |
| InvoiceDeleteDialog     | `app-invoice-delete-dialog`     | `invoice-delete-dialog/`                     | Invoice-specific delete confirmation flow.                           |
| ApplicationDeleteDialog | `app-application-delete-dialog` | `application-delete-dialog/`                 | Application delete confirmation.                                     |
| CustomerSelect          | `app-customer-select`           | `customer-select/`                           | Async customer search/select control.                                |
| ProductSelect           | `app-product-select`            | `product-select/`                            | Product selection control.                                           |
| SortableMultiSelect     | `app-sortable-multi-select`     | `sortable-multi-select/`                     | Ordered multi-select (drag/drop) for task/document flows.            |
| FileUpload              | `app-file-upload`               | `file-upload/`                               | Generic upload with progress/reset events.                           |
| MultiFileUpload         | `app-multi-file-upload`         | `multi-file-upload/`                         | Multi-file drag-and-drop upload with file list management.           |
| ImageMagnifier          | `app-image-magnifier`           | `image-magnifier/`                           | Reusable image viewer with optional hover lens magnification toggle. |
| DocumentPreview         | `app-document-preview`          | `document-preview/`                          | Inline preview launcher for uploaded docs.                           |
| PdfViewerHost           | `app-pdf-viewer-host`           | `pdf-viewer-host/`                           | Lazy PDF viewer wrapper.                                             |
| InvoiceDownloadDropdown | `app-invoice-download-dropdown` | `invoice-download-dropdown/`                 | Invoice download action menu.                                        |
| JobProgressDialog       | `app-job-progress-dialog`       | `job-progress-dialog/`                       | Async job progress modal.                                            |
| ExpiryBadge             | `app-expiry-badge`              | `expiry-badge/`                              | Date-based status badge (expiring/expired).                          |
| DashboardWidget         | `app-dashboard-widget`          | `dashboard-widget/`                          | Reusable widget container for dashboard stats/charts.                |
| FormErrorSummary        | `app-form-error-summary`        | `form-error-summary/`                        | Consolidates form validation errors into a summary block.            |
| HelpDrawer              | `z-help-drawer`                 | `help-drawer/`                               | Global contextual help + hotkeys drawer.                             |
| CalendarIntegration     | `app-calendar-integration`      | `calendar/calendar-integration.component.ts` | Calendar integration panel and sync UX.                              |
| Calendar                | `z-calendar`                    | `calendar/calendar.component.ts`             | Reusable calendar view primitives (grid/navigation/types).           |

## Reusable UI primitives (Zard-style)

These are low-level building blocks used across features:

- `avatar/`
- `badge/`
- `button/`
- `card/`
- `checkbox/`
- `combobox/`
- `command/`
- `date-input/`
- `date-picker/`
- `dialog/`
- `dropdown/`
- `empty/`
- `icon/`
- `input/`
- `input-group/`
- `loader/`
- `popover/`
- `select/`
- `sheet/`
- `skeleton/`
- `table/`
- `theme-switcher/`
- `toast/`
- `tooltip/`
- `typeahead-combobox/`

## Usage guidance

- Use composable primitives for small/contained UI.
- Use feature-level shared components for repeated business flows (tables, selectors, dialogs, upload, calendar integration).
- Keep app/page components in `features/`; move only reusable logic/UI into `shared/components/`.

## Documentation contract

When adding a new shared component, include:

When adding a new shared component, include:

- selector
- path
- intended use
- whether it is generic or domain-specific
