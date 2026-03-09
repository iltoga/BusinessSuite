# Base Components Usage Guide

## Overview

This application uses a base component architecture to reduce code duplication and ensure consistency across list, form, and detail views. The base components provide common functionality that can be inherited by specific feature components.

## Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                    Base Components                          │
├──────────────────┬──────────────────┬──────────────────────┤
│ BaseListComponent│ BaseFormComponent│ BaseDetailComponent  │
│     <T>          │ <T, Create,      │       <T>            │
│                  │     Update>      │                      │
└────────┬─────────┴────────┬─────────┴──────────┬───────────┘
         │                  │                     │
         ▼                  ▼                     ▼
  ┌─────────────┐    ┌─────────────┐     ┌─────────────┐
  │CustomerList │    │CustomerForm │     │CustomerDetail│
  │ProductList  │    │ProductForm  │     │InvoiceDetail │
  │InvoiceList  │    │             │     │             │
  │ApplicationL.│    │             │     │             │
  └─────────────┘    └─────────────┘     └─────────────┘
```

## BaseListComponent<T>

### Purpose

Provides common functionality for list views with pagination, sorting, search, and bulk operations.

### Features

- ✅ Signal-based state management
- ✅ Keyboard shortcuts (N for new, B/Left for back)
- ✅ Navigation state restoration
- ✅ Pagination, sorting, search handling
- ✅ Focus management after navigation
- ✅ Bulk delete support
- ✅ Superuser detection

### Configuration

```typescript
interface BaseListConfig<T> {
  entityType: string; // Route prefix (e.g., 'customers')
  entityLabel?: string; // Display name (e.g., 'Customers')
  defaultPageSize?: number; // Default: 10
  defaultOrdering?: string; // Default ordering field
  enableBulkDelete?: boolean;
  enableDelete?: boolean;
  newRoute?: string; // Custom new route
}
```

### Usage Example

```typescript
import { BaseListComponent, BaseListConfig } from '@/shared/core/base-list.component';
import { CustomersService, type CustomerListItem } from '@/core/services/customers.service';

@Component({
  selector: 'app-customer-list',
  templateUrl: './customer-list.component.html',
})
export class CustomerListComponent extends BaseListComponent<CustomerListItem> {
  private readonly customersService = inject(CustomersService);

  // Additional component-specific state
  readonly statusFilter = signal<'all' | 'active' | 'disabled'>('active');

  // Columns configuration
  readonly columns = computed<ColumnConfig<CustomerListItem>[]>(() => [
    { key: 'name', header: 'Name', sortable: true },
    { key: 'email', header: 'Email' },
    { key: 'actions', header: 'Actions' },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<CustomerListItem>[]>(() => [
    {
      label: 'View',
      icon: 'eye',
      variant: 'default',
      action: (item) => this.navigateToDetail(item.id),
    },
    {
      label: 'Edit',
      icon: 'settings',
      variant: 'warning',
      action: (item) => this.navigateToEdit(item.id),
    },
  ]);

  constructor() {
    super();
    this.config = {
      entityType: 'customers',
      entityLabel: 'Customers',
      defaultPageSize: 8,
      defaultOrdering: '-created_at',
      enableBulkDelete: true,
    } as BaseListConfig<CustomerListItem>;
  }

  protected override loadItems(): void {
    if (!this.isBrowser) return;

    this.isLoading.set(true);
    this.customersService
      .list({
        page: this.page(),
        pageSize: this.pageSize(),
        query: this.query() || undefined,
        ordering: this.ordering() || undefined,
        status: this.statusFilter(),
      })
      .subscribe({
        next: (response) => {
          this.items.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
          this.isLoading.set(false);
          this.focusAfterLoad();
        },
        error: () => {
          this.toast.error('Failed to load customers');
          this.isLoading.set(false);
        },
      });
  }
}
```

### Template Usage

```html
<!-- Search and filters -->
<app-search-toolbar
  [query]="query()"
  (queryChange)="onQueryChange($event)"
  (enterPressed)="onEnterSearch()"
/>

<!-- Data table -->
<app-data-table
  [data]="items()"
  [columns]="columns()"
  [actions]="actions()"
  [isLoading]="isLoading()"
  [totalItems]="totalItems()"
  [currentPage]="page()"
  [totalPages]="totalPages()"
  (pageChange)="onPageChange($event)"
  (sortChange)="onSortChange($event)"
/>

<!-- Pagination -->
<app-pagination-controls
  [currentPage]="page()"
  [totalPages]="totalPages()"
  (pageChange)="onPageChange($event)"
/>

<!-- Bulk delete dialog -->
<app-bulk-delete-dialog
  [open]="bulkDeleteOpen()"
  [data]="bulkDeleteData()"
  (confirmed)="onBulkDeleteConfirmed()"
  (cancelled)="onBulkDeleteCancelled()"
/>
```

### Available Methods

| Method                                   | Description                           |
| ---------------------------------------- | ------------------------------------- |
| `loadItems()`                            | **Abstract** - Implement to load data |
| `navigateToNew(state?)`                  | Navigate to create new item           |
| `navigateToEdit(id, state?)`             | Navigate to edit item                 |
| `navigateToDetail(id, state?)`           | Navigate to view item                 |
| `goBack()`                               | Navigate back to list                 |
| `onQueryChange(value)`                   | Handle search query change            |
| `onPageChange(page)`                     | Handle page change                    |
| `onSortChange(sort)`                     | Handle sort change                    |
| `openBulkDeleteDialog(label, details)`   | Open bulk delete dialog               |
| `handleBulkDelete(deleteFn, successMsg)` | Handle bulk delete confirmation       |
| `focusAfterLoad()`                       | Focus table or row after load         |

### Keyboard Shortcuts

| Key        | Action          |
| ---------- | --------------- |
| `N`        | Create new item |
| `B` or `←` | Go back to list |

---

## BaseFormComponent<T, CreateDto, UpdateDto>

### Purpose

Provides common functionality for create/edit forms with validation, error handling, and navigation.

### Features

- ✅ Keyboard shortcuts (Ctrl/Cmd+S to save, Escape to cancel)
- ✅ Edit mode detection from route
- ✅ Server error handling
- ✅ Navigation state management
- ✅ Loading states

### Configuration

```typescript
interface BaseFormConfig<T, CreateDto, UpdateDto> {
  entityType: string; // Route prefix (e.g., 'customers')
  entityLabel: string; // Display name (e.g., 'Customer')
  listRoute?: string; // Custom list route
  enableToasts?: boolean; // Show toast notifications
  messages?: {
    createSuccess?: string;
    updateSuccess?: string;
    loadError?: string;
    saveError?: string;
  };
}
```

### Usage Example

```typescript
import { BaseFormComponent, BaseFormConfig } from '@/shared/core/base-form.component';
import { CustomersService, type CustomerDetail } from '@/core/services/customers.service';

@Component({
  selector: 'app-customer-form',
  templateUrl: './customer-form.component.html',
})
export class CustomerFormComponent extends BaseFormComponent<
  CustomerDetail,
  CustomerCreateDto,
  CustomerUpdateDto
> {
  private readonly customersService = inject(CustomersService);

  // Additional component-specific state
  readonly countries = signal<CountryCode[]>([]);

  constructor() {
    super();
    this.config = {
      entityType: 'customers',
      entityLabel: 'Customer',
    } as BaseFormConfig<CustomerDetail, CustomerCreateDto, CustomerUpdateDto>;
  }

  protected buildForm(): FormGroup {
    return this.fb.group({
      customer_type: ['person'],
      first_name: ['', [Validators.pattern('^[A-Z][a-zA-Z\\s\\-]*$')]],
      last_name: [''],
      email: ['', Validators.email],
      // ... more fields
    });
  }

  protected loadItem(id: number): Observable<CustomerDetail> {
    return this.customersService.getCustomer(id);
  }

  protected createDto(): CustomerCreateDto {
    return this.form.value;
  }

  protected updateDto(): CustomerUpdateDto {
    return this.form.value;
  }

  protected saveCreate(dto: CustomerCreateDto): Observable<any> {
    return this.customersService.createCustomer(dto);
  }

  protected saveUpdate(dto: CustomerUpdateDto): Observable<any> {
    return this.customersService.updateCustomer(this.itemId!, dto);
  }
}
```

### Template Usage

```html
<form [formGroup]="form" (ngSubmit)="onSubmit()">
  <!-- Error summary -->
  <app-form-error-summary [form]="form" [errorLabels]="formErrorLabels" />

  <!-- Form fields -->
  <div class="space-y-4">
    <z-input
      formControlName="first_name"
      label="First Name"
      [tooltip]="fieldTooltips['first_name']"
    />

    <z-input formControlName="email" label="Email" type="email" />
  </div>

  <!-- Actions -->
  <div class="flex justify-end gap-2 mt-6">
    <button z-button zType="outline" type="button" (click)="onCancel()">Cancel</button>
    <button z-button zType="default" type="submit" [disabled]="isSaving()">
      @if (isSaving()) {
      <z-icon zType="loader-circle" class="animate-spin" />
      Saving... } @else { Save }
    </button>
  </div>
</form>
```

### Available Methods

| Method            | Description                         |
| ----------------- | ----------------------------------- |
| `buildForm()`     | **Abstract** - Create form group    |
| `loadItem(id)`    | **Abstract** - Load item for edit   |
| `createDto()`     | **Abstract** - Create DTO from form |
| `updateDto()`     | **Abstract** - Update DTO from form |
| `saveCreate(dto)` | **Abstract** - Save new item        |
| `saveUpdate(dto)` | **Abstract** - Update existing item |
| `onSubmit()`      | Handle form submission              |
| `onCancel()`      | Cancel and go back                  |
| `patchForm(item)` | Patch form with item data           |
| `goBack()`        | Navigate to list                    |

### Keyboard Shortcuts

| Key            | Action             |
| -------------- | ------------------ |
| `Ctrl/Cmd + S` | Save form          |
| `Escape`       | Cancel and go back |
| `B` or `←`     | Cancel and go back |

### Error Handling

Server errors are automatically applied to form controls:

```typescript
// Server response format expected:
{
  error: {
    errors: {
      email: ['This email is already taken'],
      first_name: ['First name is required'],
      nonFieldErrors: ['General error message']
    }
  }
}
```

The base component will:

1. Apply errors to corresponding form controls
2. Show toast notification
3. Set `isSaving` to false

---

## BaseDetailComponent<T>

### Purpose

Provides common functionality for detail/detail views with navigation, delete confirmation, and keyboard shortcuts.

### Features

- ✅ Keyboard shortcuts (E for edit, D for delete, B/Left for back)
- ✅ Navigation state management (returnUrl, searchQuery, page)
- ✅ Loading states
- ✅ Delete confirmation
- ✅ Edit navigation

### Configuration

```typescript
interface BaseDetailConfig<T> {
  entityType: string; // Route prefix (e.g., 'customers')
  entityLabel: string; // Display name (e.g., 'Customer')
  listRoute?: string; // Custom list route
  enableDelete?: boolean; // Enable delete action
  enableEdit?: boolean; // Enable edit action
  deleteRequiresSuperuser?: boolean;
  messages?: {
    loadError?: string;
    deleteConfirm?: (item: T) => string;
    deleteSuccess?: string;
    deleteError?: string;
  };
}
```

### Usage Example

```typescript
import { BaseDetailComponent, BaseDetailConfig } from '@/shared/core/base-detail.component';
import { CustomersService, type CustomerDetail } from '@/core/services/customers.service';

@Component({
  selector: 'app-customer-detail',
  templateUrl: './customer-detail.component.html',
})
export class CustomerDetailComponent extends BaseDetailComponent<CustomerDetail> {
  private readonly customersService = inject(CustomersService);

  // Additional component-specific state
  readonly applicationsHistory = signal<CustomerApplicationHistory[]>([]);

  constructor() {
    super();
    this.config = {
      entityType: 'customers',
      entityLabel: 'Customer',
      enableDelete: true,
      deleteRequiresSuperuser: true,
    } as BaseDetailConfig<CustomerDetail>;
  }

  protected loadItem(id: number): Observable<CustomerDetail> {
    return this.customersService.getCustomer(id);
  }

  protected deleteItem(id: number): Observable<any> {
    return this.customersService.deleteCustomer(id);
  }

  override ngOnInit(): void {
    // Call base initialization
    if (!this.isBrowser) return;
    this.restoreNavigationState();

    // Load additional data
    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      const id = Number(idParam);
      this.itemId = id;
      this.loadItemAndHistory(id);
    }
  }

  private loadItemAndHistory(id: number): void {
    this.isLoading.set(true);

    // Load item
    this.customersService.getCustomer(id).subscribe({
      next: (data) => {
        this.item.set(data);
      },
      error: () => {
        this.toast.error('Failed to load customer');
        this.isLoading.set(false);
      },
    });

    // Load related data
    this.customersService.getApplicationsHistory(id).subscribe({
      next: (data) => {
        this.applicationsHistory.set(data);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load applications history');
        this.isLoading.set(false);
      },
    });
  }
}
```

### Template Usage

```html
@if (isLoading()) {
<app-card-skeleton />
<app-table-skeleton />
} @else if (item()) {
<!-- Detail content -->
<z-card>
  <div class="flex justify-between items-center">
    <h2>{{ item()!.name }}</h2>

    <div class="flex gap-2">
      <z-button zType="warning" (click)="onEdit()">
        <z-icon zType="settings" />
        Edit
      </z-button>
      <z-button zType="ghost" (click)="goBack()"> Back </z-button>
    </div>
  </div>

  <!-- Detail sections -->
  <div class="mt-4 space-y-4">
    <div>
      <label class="text-sm font-medium">Email</label>
      <p>{{ item()!.email }}</p>
    </div>
  </div>
</z-card>

<!-- Related data -->
<z-card class="mt-4">
  <h3>Applications History</h3>
  <!-- Applications table -->
</z-card>
}
```

### Available Methods

| Method                     | Description                             |
| -------------------------- | --------------------------------------- |
| `loadItem(id)`             | **Abstract** - Load item from service   |
| `deleteItem(id)`           | **Abstract** - Delete item from service |
| `navigateToEdit()`         | Navigate to edit page                   |
| `goBack()`                 | Navigate back or to return URL          |
| `onDelete()`               | Handle delete with confirmation         |
| `restoreNavigationState()` | Restore state from history              |

### Keyboard Shortcuts

| Key        | Action                   |
| ---------- | ------------------------ |
| `E`        | Edit item                |
| `D`        | Delete item (if enabled) |
| `B` or `←` | Go back                  |

---

## Best Practices

### 1. Component Structure

```typescript
@Component({...})
export class MyComponent extends BaseListComponent<MyType> {
  // 1. Inject services
  private readonly myService = inject(MyService);

  // 2. Component-specific state
  readonly customFilter = signal<string>('');

  // 3. Columns/Actions (for lists)
  readonly columns = computed<ColumnConfig<MyType>[]>(() => [...]);
  override readonly actions = computed<DataTableAction<MyType>[]>(() => [...]);

  // 4. Constructor with config
  constructor() {
    super();
    this.config = { ... } as BaseListConfig<MyType>;
  }

  // 5. Implement abstract methods
  protected override loadItems(): void { ... }

  // 6. Component-specific methods
  customMethod(): void { ... }
}
```

### 2. Template Consistency

Use consistent patterns across all components:

- Search toolbar at top
- Data table in middle
- Pagination at bottom
- Bulk delete dialog

### 3. Navigation State

Always preserve navigation state when navigating between list and detail:

```typescript
// From list to detail
this.router.navigate(['/items', id], {
  state: {
    from: 'items',
    focusId: id,
    searchQuery: this.query(),
    page: this.page(),
  },
});

// From detail back to list
this.router.navigate(['/items'], {
  state: {
    focusTable: true,
    focusId: this.itemId,
    searchQuery: this.originSearchQuery(),
    page: this.originPage(),
  },
});
```

### 4. Error Handling

Use the provided error handling utilities:

```typescript
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { handleError } from '@/core/operators/handle-error.operator';

// In service calls
this.service.getData().pipe(handleError(this.toast, 'Failed to load data')).subscribe();

// Manual error extraction
error: (error) => {
  const message = extractServerErrorMessage(error);
  this.toast.error(message ?? 'Operation failed');
};
his.service.getData().pipe(handleError(this.toast, 'Failed to load data')).subscribe();

// Manual error extraction
error: (error) => {
  const message = extractServerErrorMessage(error);
  this.toast.error(message ?? 'Operation failed');
};
```

### 5. Keyboard Shortcuts

Extend keyboard shortcuts when needed:

```typescript
override handleGlobalKeydown(event: KeyboardEvent): void {
  // Call base for standard shortcuts
  super.handleGlobalKeydown(event);

  // Add custom shortcuts
  if (event.key === 'D' && !event.ctrlKey && !event.altKey) {
    event.preventDefault();
    this.customAction();
  }
}
```

---

## Testing

### Testing List Components

```typescript
describe('MyListComponent', () => {
  it('should load items on init', () => {
    const service = TestBed.inject(MyService);
    vi.spyOn(service, 'list').mockReturnValue(of({ results: [], count: 0 }));

    fixture.detectChanges();

    expect(service.list).toHaveBeenCalled();
  });

  it('should handle keyboard shortcuts', () => {
    const router = TestBed.inject(Router);
    const navigateSpy = vi.spyOn(router, 'navigate');

    const event = new KeyboardEvent('keydown', { key: 'N' });
    component.handleGlobalKeydown(event);

    expect(navigateSpy).toHaveBeenCalledWith(['/my-items/new'], expect.any(Object));
  });
});
```

### Testing Form Components

```typescript
describe('MyFormComponent', () => {
  it('should create item on submit', () => {
    component.form.patchValue({ name: 'Test' });
    const service = TestBed.inject(MyService);
    vi.spyOn(service, 'create').mockReturnValue(of({ id: 1 }));

    component.onSubmit();

    expect(service.create).toHaveBeenCalledWith({ name: 'Test' });
  });

  it('should show validation errors', () => {
    component.form.get('name')?.setErrors({ required: true });
    component.onSubmit();

    expect(component.form.get('name')?.touched).toBe(true);
  });
});
```

---

## Migration Guide

### Migrating Existing Components

1. **Identify common patterns** in your component
2. **Extend the appropriate base class**
3. **Move common logic** to base class calls
4. **Keep business-specific logic** in the component
5. **Update templates** to use base component properties
6. **Test thoroughly** to ensure no functionality is broken

### Before Migration

```typescript
@Component({...})
export class CustomerListComponent implements OnInit {
  readonly customers = signal<CustomerListItem[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  // ... 200+ lines of boilerplate

  ngOnInit(): void {
    // Manual state restoration
    const state = window.history.state;
    if (state.page) this.page.set(state.page);
    if (state.searchQuery) this.query.set(state.searchQuery);
    this.loadCustomers();
  }

  private loadCustomers(): void {
    // 30 lines of loading logic
  }
}
```

### After Migration

```typescript
@Component({...})
export class CustomerListComponent extends BaseListComponent<CustomerListItem> {
  readonly statusFilter = signal<'all' | 'active' | 'disabled'>('active');
  // Only business-specific state

  constructor() {
    super();
    this.config = { entityType: 'customers', ... };
  }

  protected override loadItems(): void {
    // Only the essential loading logic
  }
}
```

---

## Troubleshooting

### Common Issues

**Issue**: "Property 'X' is protected and only accessible within subclasses"

**Solution**: The property is intentionally protected. Access it in your component class, not in templates. Create a public getter if needed:

```typescript
get items() {
  return this.items;
}
```

**Issue**: "Cannot read properties of undefined (reading 'config')"

**Solution**: Ensure you call `super()` and set `this.config` in the constructor:

```typescript
constructor() {
  super();
  this.config = { ... };
}
```

**Issue**: "Navigation state not restored"

**Solution**: Ensure you call `this.restoreNavigationState()` in `ngOnInit()` and that you're passing state when navigating.

---

## Additional Resources

- [Base Component Source Code](./src/app/shared/core/)
- [Example Implementations](./src/app/features/customers/)
- [Unit Tests](./src/app/shared/core/*.spec.ts)
