import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { DocApplicationSerializerWithRelations } from '@/core/api/model/doc-application-serializer-with-relations';
import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  ApplicationDeleteDialogComponent,
  type ApplicationDeleteDialogData,
} from '@/shared/components/application-delete-dialog';
import { ZardBadgeImports } from '@/shared/components/badge';
import {
  BulkDeleteDialogComponent,
  type BulkDeleteDialogData,
} from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  DataTableComponent,
  type ColumnConfig,
  type ColumnFilterChangeEvent,
  type ColumnFilterOption,
  type DataTableAction,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ContextHelpDirective } from '@/shared/directives';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-application-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    DataTableComponent,
    SearchToolbarComponent,
    PaginationControlsComponent,
    ZardButtonComponent,
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
export class ApplicationListComponent implements OnInit {
  private service = inject(CustomerApplicationsService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private router = inject(Router);
  private platformId = inject(PLATFORM_ID);

  readonly items = signal<DocApplicationSerializerWithRelations[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly totalItems = signal(0);
  // default ordering: ID descending
  readonly ordering = signal<string | undefined>('-id');
  readonly columnFilters = signal<Record<string, string[]>>({
    product: [],
    status: [],
  });
  readonly isSuperuser = this.authService.isSuperuser;

  // When navigating back to the list we may want to focus a specific id or the table
  private readonly focusTableOnInit = signal(false);
  private readonly focusIdOnInit = signal<number | null>(null);

  readonly confirmOpen = signal(false);
  readonly confirmMessage = signal('');
  readonly pendingDelete = signal<DocApplicationSerializerWithRelations | null>(null);
  readonly deleteWithInvoiceOpen = signal(false);
  readonly deleteWithInvoiceData = signal<ApplicationDeleteDialogData | null>(null);

  readonly bulkDeleteOpen = signal(false);
  readonly bulkDeleteData = signal<BulkDeleteDialogData | null>(null);
  private readonly bulkDeleteQuery = signal<string>('');

  readonly bulkDeleteLabel = computed(() =>
    this.query().trim() ? 'Delete Selected Applications' : 'Delete All Applications',
  );

  private readonly customerTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnCustomer');
  private readonly productTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnProduct');
  private readonly dateTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnDate');
  private readonly statusTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnStatus');
  private readonly createdAtTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnCreatedAt');

  // Access the data table for focus management
  private readonly dataTable = viewChild.required(DataTableComponent);

  readonly columns = computed<ColumnConfig[]>(() => [
    { key: 'id', header: 'ID', sortable: true, sortKey: 'id' },
    {
      key: 'customer',
      header: 'Customer',
      sortable: true,
      sortKey: 'customer__first_name',
      template: this.customerTemplate(),
    },
    {
      key: 'product',
      header: 'Product',
      sortable: true,
      sortKey: 'product__name',
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
      header: 'Doc Date',
      sortable: true,
      sortKey: 'doc_date',
      template: this.dateTemplate(),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      sortKey: 'status',
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
      template: this.createdAtTemplate(),
    },
    { key: 'actions', header: 'Actions' },
  ]);

  readonly actions = computed<DataTableAction<DocApplicationSerializerWithRelations>[]>(() => [
    {
      label: 'Manage',
      icon: 'eye',
      variant: 'default',
      action: (item) =>
        this.router.navigate(['/applications', item.id], {
          state: { from: 'applications', focusId: item.id, searchQuery: this.query() },
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
      isVisible: (item) => Boolean(item.readyForInvoice),
      action: (item) =>
        this.router.navigate(['/invoices', 'new'], {
          queryParams: { applicationId: item.id },
          state: { from: 'applications', focusId: item.id, searchQuery: this.query() },
        }),
    },
    {
      label: 'View Invoice',
      icon: 'eye',
      variant: 'default',
      isVisible: (item) => Boolean(item.hasInvoice && item.invoiceId),
      action: (item) =>
        this.router.navigate(['/invoices', item.invoiceId], {
          state: { from: 'applications', focusId: item.id, searchQuery: this.query() },
        }),
    },
    {
      label: 'Update Invoice',
      icon: 'settings',
      variant: 'warning',
      isVisible: (item) => Boolean(item.hasInvoice && item.invoiceId),
      action: (item) =>
        this.router.navigate(['/invoices', item.invoiceId, 'edit'], {
          state: { from: 'applications', focusId: item.id, searchQuery: this.query() },
        }),
    },
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      isVisible: () => this.isSuperuser(),
      action: (item) =>
        item.hasInvoice ? this.confirmDeleteWithInvoice(item) : this.confirmDelete(item),
    },
  ]);

  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  readonly rowClassFn = (row: DocApplicationSerializerWithRelations): string =>
    row.status === 'rejected'
      ? 'row-danger-soft'
      : this.isDeprecatedProduct(row)
        ? 'opacity-60'
        : '';

  readonly filteredItems = computed(() => {
    const selectedProducts = new Set(this.columnFilters()['product'] ?? []);
    const selectedStatuses = new Set(this.columnFilters()['status'] ?? []);

    return this.items().filter((item) => {
      const productName = this.getProductLabel(item);
      const statusValue = this.getStatusValue(item);

      const productMatch = selectedProducts.size === 0 || selectedProducts.has(productName);
      const statusMatch = selectedStatuses.size === 0 || selectedStatuses.has(statusValue);
      return productMatch && statusMatch;
    });
  });

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

  readonly statusFilterOptions = computed<ColumnFilterOption[]>(() => {
    const unique = new Set<string>();
    for (const item of this.items()) {
      unique.add(this.getStatusValue(item));
    }
    return [...unique]
      .sort((a, b) => a.localeCompare(b))
      .map((value) => ({ value, label: this.getStatusLabel(value) }));
  });

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    // Shift+N for New Application
    if (event.key === 'N' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.router.navigate(['/applications', 'new'], {
        state: { from: 'applications', searchQuery: this.query() },
      });
    }
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    // Read navigation state (set by back-navigation) and remember whether we should focus the table or a specific id after load
    const st = (window as any).history.state || {};
    this.focusTableOnInit.set(Boolean(st.focusTable));
    this.focusIdOnInit.set(st.focusId ? Number(st.focusId) : null);
    if (st.searchQuery) {
      this.query.set(String(st.searchQuery));
    }
    this.load();
  }

  onQueryChange(value: string) {
    this.query.set(value.trim());
    this.page.set(1);
    this.load();
  }

  onPageChange(page: number) {
    this.page.set(page);
    this.load();
  }

  onSortChange(event: SortEvent) {
    const ordering = event.direction === 'desc' ? `-${event.column}` : event.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.load();
  }

  onColumnFilterChange(event: ColumnFilterChangeEvent): void {
    this.columnFilters.update((current) => ({
      ...current,
      [event.column]: event.values,
    }));
  }

  confirmDelete(row: DocApplicationSerializerWithRelations) {
    if (!this.isSuperuser()) {
      return;
    }
    this.pendingDelete.set(row);
    this.confirmMessage.set(`Delete application #${row.id}? This action cannot be undone.`);
    this.confirmOpen.set(true);
  }

  confirmDeleteWithInvoice(row: DocApplicationSerializerWithRelations): void {
    if (!this.isSuperuser()) {
      return;
    }
    this.pendingDelete.set(row);
    this.deleteWithInvoiceData.set({
      applicationId: row.id,
      invoiceId: row.invoiceId,
    });
    this.deleteWithInvoiceOpen.set(true);
  }

  confirmDeleteAction(): void {
    const row = this.pendingDelete();
    if (!row) {
      return;
    }

    this.service.customerApplicationsDestroy(row.id).subscribe({
      next: () => {
        this.toast.success('Application deleted');
        this.load();
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

  confirmDeleteWithInvoiceAction(): void {
    const row = this.pendingDelete();
    if (!row) {
      return;
    }

    this.service.customerApplicationsDestroy(row.id, true).subscribe({
      next: () => {
        this.toast.success('Application deleted');
        this.load();
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

  canForceClose(row: DocApplicationSerializerWithRelations): boolean {
    return !!row.canForceClose && row.status !== 'completed' && row.status !== 'rejected';
  }

  confirmForceClose(row: DocApplicationSerializerWithRelations) {
    if (!this.canForceClose(row)) {
      this.toast.error('You cannot force close this application');
      return;
    }

    if (confirm(`Force close application #${row.id}? This will mark it as completed.`)) {
      this.service.customerApplicationsForceCloseCreate(row.id, row).subscribe({
        next: () => {
          this.toast.success('Application force closed');
          this.load();
        },
        error: (err: any) => {
          const msg = err?.error?.detail || err?.error || 'Failed to force close application';
          this.toast.error(msg);
        },
      });
    }
  }

  openBulkDeleteDialog(): void {
    const query = this.query().trim();
    const mode = query ? 'selected' : 'all';
    const detailsText = query
      ? 'This will permanently remove all matching customer application records and their associated documents and workflows from the database.'
      : 'This will permanently remove all customer application records and their associated documents and workflows from the database.';

    this.bulkDeleteQuery.set(query);
    this.bulkDeleteData.set({
      entityLabel: 'Applications',
      totalCount: this.totalItems(),
      query: query || null,
      mode,
      detailsText,
    });
    this.bulkDeleteOpen.set(true);
  }

  onBulkDeleteConfirmed(): void {
    const query = this.bulkDeleteQuery();

    this.service
      .customerApplicationsBulkDeleteCreate({ searchQuery: query || '' } as any)
      .subscribe({
        next: (response) => {
          const payload = response as { deletedCount?: number; deleted_count?: number };
          const count = payload.deletedCount ?? payload.deleted_count ?? 0;
          this.toast.success(`Deleted ${count} application(s)`);
          this.bulkDeleteOpen.set(false);
          this.bulkDeleteData.set(null);
          this.bulkDeleteQuery.set('');
          this.load();
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

  onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.bulkDeleteQuery.set('');
  }

  private load(): void {
    this.isLoading.set(true);
    this.service
      .customerApplicationsList(this.ordering(), this.page(), this.pageSize(), this.query())
      .subscribe({
        next: (res) => {
          this.items.set(res.results ?? []);
          this.totalItems.set(res.count ?? 0);
          this.isLoading.set(false);

          // Focus table or a specific row if requested by navigation state
          const table = this.dataTable();
          if (table) {
            const focusId = this.focusIdOnInit();
            if (focusId) {
              this.focusIdOnInit.set(null);
              table.focusRowById(focusId);
            } else if (this.focusTableOnInit()) {
              this.focusTableOnInit.set(false);
              table.focusFirstRowIfNone();
            }
          }
        },
        error: () => {
          this.toast.error('Failed to load applications');
          this.isLoading.set(false);
        },
      });
  }

  private getProductLabel(item: DocApplicationSerializerWithRelations): string {
    return (item as any)?.product?.name?.trim() || '';
  }

  isDeprecatedProduct(item: DocApplicationSerializerWithRelations): boolean {
    return Boolean((item as any)?.product?.deprecated);
  }

  private getStatusValue(item: DocApplicationSerializerWithRelations): string {
    return (item?.status || 'pending').toString();
  }

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
