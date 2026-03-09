import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  viewChildren,
  type TemplateRef,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { InvoicesService, type InvoiceList, type PaginatedInvoiceListList } from '@/core/api';
import {
  BaseListComponent,
  BaseListConfig,
} from '@/shared/core/base-list.component';
import { ZardBadgeComponent } from '@/shared/components/badge';
import {
  BulkDeleteDialogComponent,
  type BulkDeleteDialogData,
} from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import {
  DataTableComponent,
  type ColumnConfig,
  type DataTableAction,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { ShortcutHighlightPipe } from '@/shared/components/data-table/shortcut-highlight.pipe';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent } from '@/shared/components/icon';
import {
  InvoiceDeleteDialogComponent,
  type InvoiceDeleteDialogResult,
  type InvoiceDeletePreviewData,
} from '@/shared/components/invoice-delete-dialog/invoice-delete-dialog.component';
import { InvoiceDownloadDropdownComponent } from '@/shared/components/invoice-download-dropdown/invoice-download-dropdown.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ContextHelpDirective } from '@/shared/directives';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Invoice list component
 * 
 * Extends BaseListComponent to inherit common list patterns:
 * - Keyboard shortcuts (N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management
 * - Bulk delete support
 */
@Component({
  selector: 'app-invoice-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    DataTableComponent,
    SearchToolbarComponent,
    PaginationControlsComponent,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    BulkDeleteDialogComponent,
    InvoiceDeleteDialogComponent,
    InvoiceDownloadDropdownComponent,
    ZardIconComponent,
    ShortcutHighlightPipe,
    ...ZardDropdownImports,
    ContextHelpDirective,
    AppDatePipe,
  ],
  templateUrl: './invoice-list.component.html',
  styleUrls: ['./invoice-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceListComponent extends BaseListComponent<InvoiceList> {
  private readonly invoicesApi = inject(InvoicesService);

  // Expose invoices for template compatibility
  get invoices() {
    return this.items;
  }

  // Invoice-specific state
  readonly hidePaid = signal(false);
  readonly invoiceDeleteOpen = signal(false);
  readonly invoiceDeleteData = signal<InvoiceDeletePreviewData | null>(null);
  readonly pendingInvoiceId = signal<number | null>(null);
  readonly showDownloadMenu = signal(true);

  // Template references
  private readonly numberTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'numberTemplate',
    );
  private readonly customerTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'customerTemplate',
    );
  private readonly itemsTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'itemsTemplate',
    );
  private readonly dueTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'dueTemplate',
    );
  private readonly statusTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'statusTemplate',
    );
  private readonly amountsTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'amountsTemplate',
    );
  private readonly actionsTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'actionsTemplate',
    );
  private readonly createdAtTemplate =
    viewChild.required<TemplateRef<{ $implicit: InvoiceList; value: any; row: InvoiceList }>>(
      'createdAtTemplate',
    );

  // Access the data table for focus management and row download dropdowns
  private readonly rowDownloadDropdowns = viewChildren(InvoiceDownloadDropdownComponent);

  // Invoice-specific bulk delete context
  private readonly bulkDeleteContext = signal<{ query: string; hidePaid: boolean } | null>(null);

  // Columns configuration
  readonly columns = computed<ColumnConfig<InvoiceList>[]>(() => [
    {
      key: 'invoiceNoDisplay',
      header: 'Invoice',
      sortable: true,
      sortKey: 'invoice_no',
      template: this.numberTemplate(),
    },
    { key: 'customer', header: 'Customer', template: this.customerTemplate() },
    { key: 'items', header: 'Items', template: this.itemsTemplate() },
    {
      key: 'dueDate',
      header: 'Due Date',
      sortable: true,
      sortKey: 'due_date',
      template: this.dueTemplate(),
    },
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      sortKey: 'status',
      template: this.statusTemplate(),
    },
    { key: 'amounts', header: 'Totals', template: this.amountsTemplate() },
    {
      key: 'createdAt',
      header: 'Added/Updated',
      sortable: true,
      sortKey: 'created_at',
      template: this.createdAtTemplate(),
    },
    { key: 'actions', header: 'Actions', template: this.actionsTemplate() },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<InvoiceList>[]>(() => [
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
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      isVisible: () => this.isSuperuser(),
      action: (item) => this.openInvoiceDeleteDialog(item),
    },
  ]);

  constructor() {
    super();
    this.config = {
      entityType: 'invoices',
      entityLabel: 'Invoices',
      defaultPageSize: 10,
      defaultOrdering: '-invoice_date',
      enableBulkDelete: true,
      enableDelete: true,
    } as BaseListConfig<InvoiceList>;
  }

  /**
   * Load invoices from service
   */
  protected override loadItems(): void {
    if (!this.isBrowser) return;

    this.isLoading.set(true);
    const ordering = this.ordering();

    const params: any = {
      ordering: ordering ?? undefined,
      page: this.page(),
      pageSize: this.pageSize(),
      search: this.query() || undefined,
      hidePaid: this.hidePaid() ? true : undefined,
    };

    this.invoicesApi
      .invoicesList(params.hidePaid, params.ordering, params.page, params.pageSize, params.search)
      .subscribe({
        next: (response: PaginatedInvoiceListList) => {
          this.items.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
          this.isLoading.set(false);
          this.focusAfterLoad();
        },
        error: () => {
          this.toast.error('Failed to load invoices');
          this.isLoading.set(false);
        },
      });
  }

  /**
   * Handle toggle hide paid
   */
  onToggleHidePaid(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.hidePaid.set(checked);
    this.page.set(1);
    this.loadItems();
  }

  /**
   * Format currency value
   */
  formatCurrency(value?: string | number | null): string {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (Number.isNaN(n)) return String(value ?? '—');
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      maximumFractionDigits: 0,
    }).format(n);
  }

  /**
   * Check if invoice is fully paid
   */
  isFullyPaid(row: InvoiceList): boolean {
    if (row.status === 'paid') return true;
    const due = Number(row.totalDueAmount ?? 0);
    if (!Number.isNaN(due) && due <= 0) return true;
    return false;
  }

  /**
   * Get status badge variant
   */
  statusVariant(
    status?: string | null,
  ): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
    switch (status) {
      case 'paid':
      case 'refunded':
      case 'write_off':
        return 'success';
      case 'partial_payment':
        return 'warning';
      case 'overdue':
      case 'disputed':
      case 'cancelled':
        return 'destructive';
      case 'pending_payment':
        return 'secondary';
      default:
        return 'default';
    }
  }

  /**
   * Set download menu visible
   */
  setDownloadMenuVisible(visible: boolean): void {
    this.showDownloadMenu.set(visible);
  }

  /**
   * Handle keyboard shortcuts
   */
  override handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;
    if (event.repeat) return;

    // N for New Invoice
    if (event.key === 'N' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.navigateToNew();
      return;
    }

    // P --> Print Preview on selected row
    if (event.key.toLowerCase() === 'p' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      const selected = this.dataTable().selectedRow();
      if (!selected) {
        return;
      }

      const dropdown = this.rowDownloadDropdowns().find((item) => item.invoiceId() === selected.id);
      if (!dropdown) {
        return;
      }

      event.preventDefault();
      dropdown.openPrintPreview();
    }
  }

  /**
   * Open bulk delete dialog
   */
  override openBulkDeleteDialog(): void {
    const query = this.query().trim();
    const mode = query ? 'selected' : 'all';
    const detailsText = query
      ? 'This will permanently remove all matching invoice records from the database.'
      : 'This will permanently remove all invoice records from the database.';

    this.bulkDeleteContext.set({ query, hidePaid: this.hidePaid() });
    this.bulkDeleteData.set({
      entityLabel: 'Invoices',
      totalCount: this.totalItems(),
      query: query || null,
      mode,
      detailsText,
      extraCheckboxLabel:
        'Also delete all corresponding customer applications (DocApplication) linked to the deleted invoices',
    });
    this.bulkDeleteOpen.set(true);
  }

  /**
   * Handle bulk delete confirmation
   */
  onBulkDeleteConfirmed(result: { extraChecked: boolean }): void {
    const context = this.bulkDeleteContext();
    if (!context) {
      return;
    }

    this.invoicesApi
      .invoicesBulkDeleteCreate({
        searchQuery: context.query || '',
        hidePaid: context.hidePaid,
        deleteCustomerApplications: result.extraChecked,
      })
      .subscribe({
        next: (response) => {
          const payload = response as { deletedInvoices?: number; deleted_invoices?: number };
          const count = payload.deletedInvoices ?? payload.deleted_invoices ?? 0;
          this.toast.success(`Deleted ${count} invoice(s)`);
          this.bulkDeleteOpen.set(false);
          this.bulkDeleteData.set(null);
          this.bulkDeleteContext.set(null);
          this.loadItems();
        },
        error: (error) => {
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to delete invoices: ${message}` : 'Failed to delete invoices',
          );
          this.bulkDeleteOpen.set(false);
          this.bulkDeleteData.set(null);
          this.bulkDeleteContext.set(null);
        },
      });
  }

  /**
   * Handle bulk delete cancellation
   */
  override onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.bulkDeleteContext.set(null);
  }

  /**
   * Open invoice delete dialog
   */
  openInvoiceDeleteDialog(invoice: InvoiceList): void {
    if (!this.isSuperuser()) {
      return;
    }

    this.pendingInvoiceId.set(invoice.id);
    this.invoicesApi.invoicesDeletePreviewRetrieve(invoice.id).subscribe({
      next: (response) => {
        const payload = response as {
          invoiceNoDisplay?: string;
          invoice_no_display?: string;
          customerName?: string;
          customer_name?: string;
          totalAmount?: string | number;
          total_amount?: string | number;
          statusDisplay?: string;
          status_display?: string;
          invoiceApplicationsCount?: number;
          invoice_applications_count?: number;
          customerApplicationsCount?: number;
          customer_applications_count?: number;
          paymentsCount?: number;
          payments_count?: number;
        };

        this.invoiceDeleteData.set({
          invoiceNoDisplay:
            payload.invoiceNoDisplay ??
            payload.invoice_no_display ??
            invoice.invoiceNoDisplay ??
            '',
          customerName:
            payload.customerName ??
            payload.customer_name ??
            invoice.customer?.fullNameWithCompany ??
            invoice.customer?.fullName ??
            '—',
          totalAmount: payload.totalAmount ?? payload.total_amount ?? invoice.totalAmount ?? '—',
          statusDisplay: payload.statusDisplay ?? payload.status_display ?? invoice.status ?? '—',
          invoiceApplicationsCount:
            payload.invoiceApplicationsCount ?? payload.invoice_applications_count ?? 0,
          customerApplicationsCount:
            payload.customerApplicationsCount ?? payload.customer_applications_count ?? 0,
          paymentsCount: payload.paymentsCount ?? payload.payments_count ?? 0,
        });
        this.invoiceDeleteOpen.set(true);
      },
      error: () => {
        this.toast.error('Failed to load delete preview');
        this.pendingInvoiceId.set(null);
      },
    });
  }

  /**
   * Handle invoice delete confirmation
   */
  onInvoiceDeleteConfirmed(result: InvoiceDeleteDialogResult): void {
    const invoiceId = this.pendingInvoiceId();
    if (!invoiceId) {
      return;
    }

    this.invoicesApi
      .invoicesForceDeleteCreate(invoiceId, {
        forceDeleteConfirmed: true,
        deleteCustomerApplications: result.deleteCustomerApplications,
      })
      .subscribe({
        next: () => {
          this.toast.success('Invoice deleted');
          this.invoiceDeleteOpen.set(false);
          this.invoiceDeleteData.set(null);
          this.pendingInvoiceId.set(null);
          this.loadItems();
        },
        error: (error) => {
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to delete invoice: ${message}` : 'Failed to delete invoice',
          );
          this.invoiceDeleteOpen.set(false);
          this.invoiceDeleteData.set(null);
          this.pendingInvoiceId.set(null);
        },
      });
  }

  /**
   * Handle invoice delete cancellation
   */
  onInvoiceDeleteCancelled(): void {
    this.invoiceDeleteOpen.set(false);
    this.invoiceDeleteData.set(null);
    this.pendingInvoiceId.set(null);
  }
}
