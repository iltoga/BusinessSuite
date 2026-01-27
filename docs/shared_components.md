# Shared Components Registry

## Rules of Engagement

- **ALWAYS** check this list before building a new UI component
- If a component exists here, reuse it; do not rebuild
- Document new shared components immediately after creation

## Component Index

> **UI note:** Prefer using `z-combobox` (searchable combobox) for long/static lists where typeahead improves UX (e.g., country, customer, product selections). Use the standard select only for short, non-searchable lists. This helps provide consistent keyboard navigation, search filtering, and accessibility across forms.

| Component Name      | Selector                  | Location                                        | ZardUI Deps    | Status   |
| ------------------- | ------------------------- | ----------------------------------------------- | -------------- | -------- |
| DataTable           | app-data-table            | src/app/shared/components/data-table            | Table          | ✅ Ready |
| ConfirmDialog       | app-confirm-dialog        | src/app/shared/components/confirm-dialog        | Dialog, Button | ✅ Ready |
| SearchToolbar       | app-search-toolbar        | src/app/shared/components/search-toolbar        | Input, Button  | ✅ Ready |
| Pagination          | app-pagination-controls   | src/app/shared/components/pagination-controls   | Button, Icon   | ✅ Ready |
| ExpiryBadge         | app-expiry-badge          | src/app/shared/components/expiry-badge          | Badge          | ✅ Ready |
| FileUpload          | app-file-upload           | src/app/shared/components/file-upload           | Button         | ✅ Ready |
| DocumentPreview     | app-document-preview      | src/app/shared/components/document-preview      | Popover, Icon  | ✅ Ready |
| SortableMultiSelect | app-sortable-multi-select | src/app/shared/components/sortable-multi-select | DragDrop       | ✅ Ready |

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

### SortableMultiSelectComponent

**Location:** `src/app/shared/components/sortable-multi-select/sortable-multi-select.component.ts`

**Interface:**

```typescript
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
```
