import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  viewChild,
  type TemplateRef,
} from '@angular/core';
import { RouterLink } from '@angular/router';
import { type Observable } from 'rxjs';

import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { DocApplicationList } from '@/core/api/model/doc-application-list';
import { unwrapApiRecord } from '@/core/utils/api-envelope';
import {
  ApplicationDeleteDialogComponent,
  type ApplicationDeleteDialogData,
} from '@/shared/components/application-delete-dialog';
import { ZardBadgeImports } from '@/shared/components/badge';
import { BulkDeleteDialogComponent } from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  DataTableComponent,
  type ColumnConfig,
  type ColumnFilterChangeEvent,
  type ColumnFilterOption,
  type DataTableAction,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import {
  BaseListComponent,
  BaseListConfig,
  type ListRequestParams,
  type PaginatedResponse,
} from '@/shared/core/base-list.component';
import { ContextHelpDirective } from '@/shared/directives';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Application list component
 *
 * Extends BaseListComponent to inherit common list patterns:
 * - Keyboard shortcuts (N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management
 * - Bulk delete support
 */
@Component({
  selector: 'app-application-list',
  standalone: true,
  imports: [
    RouterLink,
    DataTableComponent,
    SearchToolbarComponent,
    PaginationControlsComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ApplicationDeleteDialogComponent,
    ConfirmDialogComponent,
    BulkDeleteDialogComponent,
    ...ZardBadgeImports,
    ContextHelpDirective,
    AppDatePipe,
  ],
  templateUrl: './application-list.component.html',
  styleUrls: ['./application-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationListComponent extends BaseListComponent<DocApplicationList> {
  private readonly service = inject(CustomerApplicationsService);
  readonly isAdminOrManager = this.authService.isAdminOrManager;

  // Application-specific state
  readonly confirmOpen = signal(false);
  readonly confirmMessage = signal('');
  readonly pendingDelete = signal<DocApplicationList | null>(null);
  readonly deleteWithInvoiceOpen = signal(false);
  readonly deleteWithInvoiceData = signal<ApplicationDeleteDialogData | null>(null);

  // Template references
  private readonly customerTemplate =
    viewChild.required<TemplateRef<{ $implicit: DocApplicationList; value: any; row: any }>>(
      'columnCustomer',
    );
  private readonly productTemplate =
    viewChild.required<TemplateRef<{ $implicit: DocApplicationList; value: any; row: any }>>(
      'columnProduct',
    );
  private readonly dateTemplate =
    viewChild.required<TemplateRef<{ $implicit: DocApplicationList; value: any; row: any }>>(
      'columnDate',
    );
  private readonly statusTemplate =
    viewChild.required<TemplateRef<{ $implicit: DocApplicationList; value: any; row: any }>>(
      'columnStatus',
    );
  private readonly createdAtTemplate =
    viewChild.required<TemplateRef<{ $implicit: DocApplicationList; value: any; row: any }>>(
      'columnCreatedAt',
    );

  // Application-specific bulk delete query
  private readonly applicationBulkDeleteQuery = signal<string>('');

  // Columns configuration
  readonly columns = computed<ColumnConfig[]>(() => [
    { key: 'id', header: 'ID', sortable: true, sortKey: 'id', width: '5%' },
    {
      key: 'customer',
      header: 'Customer',
      sortable: true,
      sortKey: 'customer__first_name',
      width: '22%',
      template: this.customerTemplate(),
    },
    {
      key: 'product',
      header: 'Product',
      sortable: true,
      sortKey: 'product__name',
      width: '20%',
      template: this.productTemplate(),
      filter: {
        options: this.productFilterOptions(),
        selectedValues: this.columnFilters()['product'] ?? [],
        emptyLabel: 'No products found',
        searchPlaceholder: 'Search products...',
      },
    },
    {
      key: 'docDate',
      header: 'Submission Date',
      subtitle: 'Last Date',
      sortable: true,
      sortKey: 'doc_date',
      width: '16%',
      template: this.dateTemplate(),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      sortKey: 'status',
      width: '12%',
      template: this.statusTemplate(),
      filter: {
        options: this.statusFilterOptions(),
        selectedValues: this.columnFilters()['status'] ?? [],
        emptyLabel: 'No statuses found',
        searchPlaceholder: 'Search statuses...',
      },
    },
    {
      key: 'createdAt',
      header: 'Added/Updated',
      sortable: true,
      sortKey: 'created_at',
      width: '16%',
      template: this.createdAtTemplate(),
    },
    { key: 'actions', header: 'Actions', width: '4%' },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<DocApplicationList>[]>(() => [
    {
      label: 'Manage',
      icon: 'eye',
      variant: 'default',
      action: (item) =>
        this.router.navigate(['/applications', item.id], {
          state: this.applicationDetailState(item),
        }),
    },
    {
      label: 'Force Close',
      icon: 'ban',
      variant: 'outline',
      isVisible: (item) => this.canForceClose(item),
      action: (item) => this.confirmForceClose(item),
    },
    {
      label: 'Create Invoice',
      icon: 'plus',
      variant: 'success',
      shortcut: 'i',
      isVisible: (item) => this.canCreateInvoice(item),
      action: (item) =>
        this.router.navigate(['/invoices', 'new'], {
          queryParams: { applicationId: item.id },
          state: this.applicationDetailState(item),
        }),
    },
    {
      label: 'View Invoice',
      icon: 'eye',
      variant: 'default',
      isVisible: (item) => Boolean(item.hasInvoice && item.invoiceId),
      action: (item) =>
        this.router.navigate(['/invoices', item.invoiceId], {
          state: this.applicationDetailState(item),
        }),
    },
    {
      label: 'Update Invoice',
      icon: 'settings',
      variant: 'warning',
      isVisible: (item) => Boolean(item.hasInvoice && item.invoiceId),
      action: (item) =>
        this.router.navigate(['/invoices', item.invoiceId, 'edit'], {
          state: this.applicationDetailState(item),
        }),
    },
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      isVisible: () => this.isAdminOrManager(),
      action: (item) =>
        item.hasInvoice ? this.confirmDeleteWithInvoice(item) : this.confirmDelete(item),
    },
  ]);

  // Row class for rejected or deprecated products
  readonly rowClassFn = (row: DocApplicationList): string =>
    row.status === 'rejected' ? 'row-danger-soft' : '';

  // Filtered items based on column filters
  readonly filteredItems = computed(() => {
    const selectedProducts = new Set(this.columnFilters()['product'] ?? []);
    const selectedStatuses = new Set(this.columnFilters()['status'] ?? []);

    return this.items().filter((item: DocApplicationList) => {
      const productName = this.getProductLabel(item);
      const statusValue = this.getStatusValue(item);

      const productMatch = selectedProducts.size === 0 || selectedProducts.has(productName);
      const statusMatch = selectedStatuses.size === 0 || selectedStatuses.has(statusValue);
      return productMatch && statusMatch;
    });
  });

  // Product filter options
  readonly productFilterOptions = computed<ColumnFilterOption[]>(() => {
    const unique = new Set<string>();
    for (const item of this.items()) {
      const label = this.getProductLabel(item);
      if (label) {
        unique.add(label);
      }
    }
    return [...unique].sort((a, b) => a.localeCompare(b)).map((value) => ({ value, label: value }));
  });

  // Status filter options
  readonly statusFilterOptions = computed<ColumnFilterOption[]>(() => {
    const unique = new Set<string>();
    for (const item of this.items()) {
      unique.add(this.getStatusValue(item));
    }
    return [...unique]
      .sort((a, b) => a.localeCompare(b))
      .map((value) => ({ value, label: this.getStatusLabel(value) }));
  });

  constructor() {
    super();
    this.columnFilters.set({
      product: [],
      status: [],
    });
    // Setup base config
    this.config = {
      entityType: 'applications',
      entityLabel: 'Applications',
      defaultPageSize: 11,
      defaultOrdering: '-id',
      enableBulkDelete: true,
      enableDelete: true,
    } as BaseListConfig<DocApplicationList>;
  }

  /**
   * Create the Observable that fetches a page of applications.
   */
  protected override createListLoader(
    params: ListRequestParams,
  ): Observable<PaginatedResponse<DocApplicationList>> {
    return this.service.customerApplicationsList(
      params.ordering,
      params.page,
      params.pageSize,
      params.query,
    );
  }

  /**
   * Confirm delete for an application
   */
  confirmDelete(row: DocApplicationList) {
    if (!this.isAdminOrManager()) {
      return;
    }
    this.pendingDelete.set(row);
    this.confirmMessage.set(`Delete application #${row.id}? This action cannot be undone.`);
    this.confirmOpen.set(true);
  }

  /**
   * Confirm delete with invoice
   */
  confirmDeleteWithInvoice(row: DocApplicationList): void {
    if (!this.isAdminOrManager()) {
      return;
    }
    this.pendingDelete.set(row);
    this.deleteWithInvoiceData.set({
      applicationId: row.id,
      invoiceId: row.invoiceId,
    });
    this.deleteWithInvoiceOpen.set(true);
  }

  /**
   * Confirm delete action
   */
  confirmDeleteAction(): void {
    const row = this.pendingDelete();
    if (!row) {
      return;
    }

    this.service.customerApplicationsDestroy(row.id).subscribe({
      next: () => {
        this.toast.success('Application deleted');
        this.reload();
        this.confirmOpen.set(false);
        this.pendingDelete.set(null);
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete application: ${message}` : 'Failed to delete application',
        );
        this.confirmOpen.set(false);
        this.pendingDelete.set(null);
      },
    });
  }

  /**
   * Cancel delete action
   */
  cancelDeleteAction(): void {
    const row = this.pendingDelete();
    this.confirmOpen.set(false);
    this.pendingDelete.set(null);

    // Return focus to the row that was being acted on
    if (row) {
      const table = this.dataTable();
      if (table) {
        table.focusRowById(row.id);
      }
    }
  }

  /**
   * Confirm delete with invoice action
   */
  confirmDeleteWithInvoiceAction(): void {
    const row = this.pendingDelete();
    if (!row) {
      return;
    }

    this.service.customerApplicationsDestroy(row.id, true).subscribe({
      next: () => {
        this.toast.success('Application deleted');
        this.reload();
        this.deleteWithInvoiceOpen.set(false);
        this.deleteWithInvoiceData.set(null);
        this.pendingDelete.set(null);
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete application: ${message}` : 'Failed to delete application',
        );
        this.deleteWithInvoiceOpen.set(false);
        this.deleteWithInvoiceData.set(null);
        this.pendingDelete.set(null);
      },
    });
  }

  /**
   * Cancel delete with invoice action
   */
  cancelDeleteWithInvoiceAction(): void {
    const row = this.pendingDelete();
    this.deleteWithInvoiceOpen.set(false);
    this.deleteWithInvoiceData.set(null);
    this.pendingDelete.set(null);

    // Return focus to the row that was being acted on
    if (row) {
      const table = this.dataTable();
      if (table) {
        table.focusRowById(row.id);
      }
    }
  }

  /**
   * Check if application can be force closed
   */
  canForceClose(row: DocApplicationList): boolean {
    return !!row.canForceClose && row.status !== 'completed' && row.status !== 'rejected';
  }

  /**
   * Check if invoice can be created
   */
  canCreateInvoice(row: DocApplicationList): boolean {
    return !row.hasInvoice;
  }

  /**
   * Confirm force close application
   */
  confirmForceClose(row: DocApplicationList) {
    if (!this.canForceClose(row)) {
      this.toast.error('You cannot force close this application');
      return;
    }

    if (confirm(`Force close application #${row.id}? This will mark it as completed.`)) {
      this.service.customerApplicationsForceCloseCreate(row.id).subscribe({
        next: () => {
          this.toast.success('Application force closed');
          this.reload();
        },
        error: (err: any) => {
          const msg = err?.error?.detail || err?.error || 'Failed to force close application';
          this.toast.error(msg);
        },
      });
    }
  }

  /**
   * Build application detail state
   */
  applicationDetailState(item: DocApplicationList): Record<string, unknown> {
    return {
      from: 'applications',
      focusId: item.id,
      searchQuery: this.query(),
      page: this.page(),
    };
  }

  /**
   * Open bulk delete dialog
   */
  override openBulkDeleteDialog(): void {
    const query = this.query().trim();
    const mode = this.hasAnyFilter() ? 'selected' : 'all';
    const detailsText = this.hasAnyFilter()
      ? 'This will permanently remove all matching customer application records and their associated documents and workflows from the database.'
      : 'This will permanently remove all customer application records and their associated documents and workflows from the database.';

    this.applicationBulkDeleteQuery.set(query);
    this.bulkDeleteData.set({
      entityLabel: 'Applications',
      totalCount: this.totalItems(),
      query: query || null,
      mode,
      detailsText,
    });
    this.bulkDeleteOpen.set(true);
  }

  /**
   * Handle bulk delete confirmation
   */
  onBulkDeleteConfirmed(): void {
    const query = this.applicationBulkDeleteQuery();
    const bulkDeletePayload = {
      searchQuery: query || '',
    } as unknown as Parameters<
      CustomerApplicationsService['customerApplicationsBulkDeleteCreate']
    >[0];

    this.service
      .customerApplicationsBulkDeleteCreate(bulkDeletePayload)
      .subscribe({
        next: (response) => {
          const payload = unwrapApiRecord(response) as {
            deletedCount?: number;
            deleted_count?: number;
          } | null;
          const count = payload?.deletedCount ?? payload?.deleted_count ?? 0;
          this.toast.success(`Deleted ${count} application(s)`);
          this.bulkDeleteOpen.set(false);
          this.bulkDeleteData.set(null);
          this.applicationBulkDeleteQuery.set('');
          this.reload();
        },
        error: (error) => {
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to delete applications: ${message}` : 'Failed to delete applications',
          );
          this.bulkDeleteOpen.set(false);
          this.bulkDeleteData.set(null);
        },
      });
  }

  /**
   * Handle bulk delete cancellation
   */
  override onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.applicationBulkDeleteQuery.set('');
  }

  /**
   * Get product label from item
   */
  private getProductLabel(item: DocApplicationList): string {
    return (item as any)?.product?.name?.trim() || '';
  }

  /**
   * Check if product is deprecated
   */
  isDeprecatedProduct(item: DocApplicationList): boolean {
    return Boolean((item as any)?.product?.deprecated);
  }

  /**
   * Get status value from item
   */
  private getStatusValue(item: DocApplicationList): string {
    return (item?.status || 'pending').toString();
  }

  /**
   * Get status label
   */
  private getStatusLabel(value: string): string {
    switch (value) {
      case 'completed':
        return 'Completed';
      case 'processing':
        return 'Processing';
      case 'rejected':
        return 'Rejected';
      default:
        return 'Pending';
    }
  }
}
