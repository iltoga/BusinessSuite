# Shared Components Registry

## Rules of Engagement

- **ALWAYS** check this list before building a new UI component
- If a component exists here, reuse it; do not rebuild
- Document new shared components immediately after creation

## Component Index

> **UI note:** Prefer using `z-combobox` (searchable combobox) for long/static lists where typeahead improves UX (e.g., country, customer, product selections). Use the standard select only for short, non-searchable lists. This helps provide consistent keyboard navigation, search filtering, and accessibility across forms.

| Component Name      | Selector                  | Location                                        | ZardUI Deps             | Status          |
| ------------------- | ------------------------- | ----------------------------------------------- | ----------------------- | --------------- |
| DataTable           | app-data-table            | src/app/shared/components/data-table            | Table                   | ✅ Ready        |
| ConfirmDialog       | app-confirm-dialog        | src/app/shared/components/confirm-dialog        | Dialog, Button          | ✅ Ready        |
| SearchToolbar       | app-search-toolbar        | src/app/shared/components/search-toolbar        | Input, Button           | ✅ Ready        |
| Pagination          | app-pagination-controls   | src/app/shared/components/pagination-controls   | Button, Icon            | ✅ Ready        |
| ExpiryBadge         | app-expiry-badge          | src/app/shared/components/expiry-badge          | Badge                   | ✅ Ready        |
| BulkDeleteDialog    | app-bulk-delete-dialog    | src/app/shared/components/bulk-delete-dialog    | Dialog, Button          | ✅ Ready        |
| InvoiceDeleteDialog | app-invoice-delete-dialog | src/app/shared/components/invoice-delete-dialog | Dialog, Button          | ✅ Ready        |
| FileUpload          | app-file-upload           | src/app/shared/components/file-upload           | Button                  | ✅ Ready        |
| DocumentPreview     | app-document-preview      | src/app/shared/components/document-preview      | Popover, Icon           | ✅ Ready        |
| PdfViewerHost       | app-pdf-viewer-host       | src/app/shared/components/pdf-viewer-host       | ngx-extended-pdf-viewer | ✅ Ready (lazy) |
| SortableMultiSelect | app-sortable-multi-select | src/app/shared/components/sortable-multi-select | DragDrop                | ✅ Ready        |
| CustomerSelect      | app-customer-select       | src/app/shared/components/customer-select       | Combobox                | ✅ Ready        |
| TableSkeleton       | app-table-skeleton        | src/app/shared/components/skeleton              | Table, Skeleton         | ✅ Ready        |
| CardSkeleton        | app-card-skeleton         | src/app/shared/components/skeleton              | Card, Skeleton          | ✅ Ready        |

## Component Details

### DataTableComponent

**Location:** `src/app/shared/components/data-table/data-table.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-data-table",
  standalone: true,
})
export class DataTableComponent<T> {
  data = input.required<readonly T[]>();
  columns = input.required<readonly ColumnConfig[]>();
  totalItems = input<number>(0);
  isLoading = input<boolean>(false);
  pageChange = output<PageEvent>();
  sortChange = output<SortEvent>();
}
```

**ColumnConfig:**

```typescript
export interface ColumnConfig {
  key: string;
  header: string;
  sortable?: boolean;
  sortKey?: string;
  template?: TemplateRef<unknown>;
}
```

### ConfirmDialogComponent

**Location:** `src/app/shared/components/confirm-dialog/confirm-dialog.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-confirm-dialog",
  standalone: true,
})
export class ConfirmDialogComponent {
  isOpen = input<boolean>(false);
  title = input<string>("Confirm Action");
  message = input<string>("Are you sure?");
  confirmText = input<string>("Confirm");
  cancelText = input<string>("Cancel");
  destructive = input<boolean>(false);
  confirmed = output<void>();
  cancelled = output<void>();
}
```

### SearchToolbarComponent

**Location:** `src/app/shared/components/search-toolbar/search-toolbar.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-search-toolbar",
  standalone: true,
})
export class SearchToolbarComponent {
  query = input<string>("");
  placeholder = input<string>("Search...");
  debounceMs = input<number>(500);
  isLoading = input<boolean>(false);
  disabled = input<boolean>(false);
  queryChange = output<string>();
  submitted = output<string>();
}
```

### BulkDeleteDialogComponent

**Location:** `src/app/shared/components/bulk-delete-dialog/bulk-delete-dialog.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-bulk-delete-dialog",
  standalone: true,
})
export class BulkDeleteDialogComponent {
  isOpen = input<boolean>(false);
  data = input<BulkDeleteDialogData | null>(null);
  confirmed = output<BulkDeleteDialogResult>();
  cancelled = output<void>();
}
```

**Notes:** Use for delete-all/selected confirmation dialogs with optional cascade checkbox.

### InvoiceDeleteDialogComponent

**Location:** `src/app/shared/components/invoice-delete-dialog/invoice-delete-dialog.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-invoice-delete-dialog",
  standalone: true,
})
export class InvoiceDeleteDialogComponent {
  isOpen = input<boolean>(false);
  data = input<InvoiceDeletePreviewData | null>(null);
  confirmed = output<InvoiceDeleteDialogResult>();
  cancelled = output<void>();
}
```

**Notes:** Matches legacy invoice force-delete flow with mandatory confirmation checkbox and cascade preview.

### PaginationControlsComponent

**Location:** `src/app/shared/components/pagination-controls/pagination-controls.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-pagination-controls",
  standalone: true,
})
export class PaginationControlsComponent {
  page = input<number>(1);
  totalPages = input<number>(1);
  disabled = input<boolean>(false);
  pageChange = output<number>();
}
```

### ExpiryBadgeComponent

**Location:** `src/app/shared/components/expiry-badge/expiry-badge.component.ts`

**Interface:**

````typescript
@Component({
  selector: "app-expiry-badge",
  standalone: true,
})
export class ExpiryBadgeComponent {
  date = input<string | Date | null>(null);
  warningDays = input<number>(183);
  emptyLabel = input<string>("—");
}

### FileUploadComponent

**Location:** `src/app/shared/components/file-upload/file-upload.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-file-upload",
  standalone: true,
})
export class FileUploadComponent {
  label = input<string>("Upload file");
  accept = input<string>("*/*");
  disabled = input<boolean>(false);
  progress = input<number | null>(null);
  fileName = input<string | null>(null);
  helperText = input<string | null>(null);
  fileSelected = output<File>();
  cleared = output<void>();
}
````

### DocumentPreviewComponent

**Location:** `src/app/shared/components/document-preview/document-preview.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-document-preview",
  standalone: true,
})
export class DocumentPreviewComponent {
  documentId = input.required<number>();
  fileLink = input<string | null>(null);
  label = input<string>("Preview");
  zType = input<ZardButtonTypeVariants>("outline");
  zSize = input<ZardButtonSizeVariants>("sm");
  viewFull = output<void>();
}
```

**Behavior:** For image files (PNG/JPG) it shows an inline thumbnail. For PDFs it shows a small PDF icon and a "View Full" button which opens a lazily-loaded full PDF viewer.

---

### PdfViewerHostComponent

**Location:** `src/app/shared/components/pdf-viewer-host/pdf-viewer-host.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-pdf-viewer-host",
  standalone: true,
  imports: [NgxExtendedPdfViewerModule],
})
export class PdfViewerHostComponent {
  src = input<Blob | string | null>(null);
  closed = output<void>();
}
```

**Notes:** This component is intended to be lazy-loaded and created dynamically by `DocumentPreviewComponent` to avoid shipping the PDF viewer until needed. It accepts a `Blob` or object-URL as `src` and emits `closed` when the user closes the overlay.

**Important (server config):** Ensure the ngx-extended-pdf-viewer assets are available under `/assets/` (avoid SPA fallback to index.html). This project copies `node_modules/ngx-extended-pdf-viewer/assets/` into `/assets/` via `angular.json` and configures `pdfDefaultOptions.assetsFolder = 'assets'` and `pdfDefaultOptions.workerSrc = () => '/assets/pdf.worker-5.4.1105.min.mjs'`. This prevents the "Expected a JavaScript-or-Wasm module script but the server responded with a MIME type of 'text/html'" error when the dev server returns `index.html` for missing asset paths.

### SortableMultiSelectComponent

**Location:** `src/app/shared/components/sortable-multi-select/sortable-multi-select.component.ts`

**Interface:**

````typescript
@Component({
  selector: "app-sortable-multi-select",
  standalone: true,
})
export class SortableMultiSelectComponent {
  options = input.required<readonly { id: number; label: string }[]>();
  selectedIds = input<number[]>([]);
  label = input<string>("");
  selectedIdsChange = output<number[]>();
}

### CustomerSelectComponent

**Location:** `src/app/shared/components/customer-select/customer-select.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-customer-select",
  standalone: true,
})
export class CustomerSelectComponent {
  label = input<string>("Customer");
  placeholder = input<string>("Select a customer...");
  searchPlaceholder = input<string>("Search customers...");
  selectedId = input<number | null>(null);
  selectedIdChange = output<number | null>();
}
````

### TableSkeletonComponent

**Location:** `src/app/shared/components/skeleton/table-skeleton.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-table-skeleton",
  standalone: true,
})
export class TableSkeletonComponent {
  columns = input<number>(5);
  rows = input<number>(5);
}
```

### CardSkeletonComponent

**Location:** `src/app/shared/components/skeleton/card-skeleton.component.ts`

**Interface:**

```typescript
@Component({
  selector: "app-card-skeleton",
  standalone: true,
})
export class CardSkeletonComponent {
  showHeader = input<boolean>(true);
  lines = input<number>(3);
}
```

## Updates

- **2026-01-30:** Added `TableSkeletonComponent` and `CardSkeletonComponent` to handle loading states in list and detail views.
- **2026-01-29:** Letters (Surat Permohonan) feature reused existing shared components; no new shared components added.
- **2026-01-29:** Invoices & Payments feature added new invoice screens; no new shared components added.

```

```
