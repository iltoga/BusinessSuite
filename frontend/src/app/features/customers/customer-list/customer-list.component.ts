import { CommonModule } from '@angular/common';
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

import type { Customer } from '@/core/api';
import { CustomersService } from '@/core/services/customers.service';
import { ZardBadgeComponent } from '@/shared/components/badge/badge.component';
import { BulkDeleteDialogComponent } from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import {
  DataTableComponent,
  type ColumnConfig,
  type DataTableAction,
} from '@/shared/components/data-table/data-table.component';
import { ExpiryBadgeComponent } from '@/shared/components/expiry-badge';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardSelectImports } from '@/shared/components/select';
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
 * Customer list component
 *
 * Extends BaseListComponent to inherit common list patterns:
 * - Keyboard shortcuts (N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management
 * - Bulk delete support
 */
@Component({
  selector: 'app-customer-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    DataTableComponent,
    SearchToolbarComponent,
    PaginationControlsComponent,
    ExpiryBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    BulkDeleteDialogComponent,
    ...ZardSelectImports,
    ZardBadgeComponent,
    ContextHelpDirective,
    AppDatePipe,
  ],
  templateUrl: './customer-list.component.html',
  styleUrls: ['./customer-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerListComponent extends BaseListComponent<Customer> {
  private readonly customersService = inject(CustomersService);

  // Expose items as customers for template compatibility
  get customers() {
    return this.items;
  }

  // Additional state not handled by base class
  readonly statusFilter = signal<'all' | 'active' | 'disabled'>('active');
  private readonly bulkDeleteContext = signal<{
    query: string;
    status: 'all' | 'active' | 'disabled';
  } | null>(null);

  // Template references for columns
  private readonly customerTemplate =
    viewChild.required<TemplateRef<{ $implicit: Customer; value: any; row: Customer }>>(
      'customerTemplate',
    );
  private readonly passportTemplate =
    viewChild.required<TemplateRef<{ $implicit: Customer; value: any; row: Customer }>>(
      'passportTemplate',
    );
  private readonly emailTemplate =
    viewChild.required<TemplateRef<{ $implicit: Customer; value: any; row: Customer }>>(
      'emailTemplate',
    );
  private readonly whatsappTemplate =
    viewChild.required<TemplateRef<{ $implicit: Customer; value: any; row: Customer }>>(
      'whatsappTemplate',
    );
  private readonly nationalityTemplate =
    viewChild.required<TemplateRef<{ $implicit: Customer; value: any; row: Customer }>>(
      'nationalityTemplate',
    );
  private readonly createdAtTemplate =
    viewChild.required<TemplateRef<{ $implicit: Customer; value: any; row: Customer }>>(
      'createdAtTemplate',
    );

  // Columns configuration
  readonly columns = computed<ColumnConfig<Customer>[]>(() => [
    {
      key: 'fullNameWithCompany',
      header: 'Customer',
      sortable: true,
      sortKey: 'last_name',
      width: '22%',
      template: this.customerTemplate(),
    },
    {
      key: 'passportNumber',
      header: 'Passport',
      subtitle: 'Valid till',
      width: '12%',
      template: this.passportTemplate(),
    },
    {
      key: 'nationalityName',
      header: 'Nationality',
      sortable: true,
      sortKey: 'nationality__country',
      width: '12%',
      template: this.nationalityTemplate(),
    },
    {
      key: 'email',
      header: 'Email',
      sortable: true,
      sortKey: 'email',
      width: '24%',
      template: this.emailTemplate(),
    },
    {
      key: 'whatsapp',
      header: 'WhatsApp',
      width: '10%',
      template: this.whatsappTemplate(),
    },
    {
      key: 'createdAt',
      header: 'Added/Updated',
      sortable: true,
      sortKey: 'created_at',
      width: '12%',
      template: this.createdAtTemplate(),
    },
    {
      key: 'actions',
      header: 'Actions',
      width: '4%',
    },
  ]);

  // Actions configuration
  override readonly actions = computed<DataTableAction<Customer>[]>(() => {
    const actions: DataTableAction<Customer>[] = [
      {
        label: 'View Detail',
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
        label: 'Toggle Active',
        icon: 'ban',
        variant: 'default',
        action: (item) => this.onToggleActive(item),
      },
      {
        label: 'New Application',
        icon: 'plus',
        variant: 'success',
        shortcut: 'a',
        action: (item) =>
          this.router.navigate(['/customers', item.id, 'applications', 'new'], {
            state: this.navigationState(item.id),
          }),
      },
    ];

    if (this.isSuperuser()) {
      actions.push({
        label: 'Delete',
        icon: 'trash',
        variant: 'destructive',
        action: (item) => this.onDelete(item),
        isDestructive: true,
      });
    }

    return actions;
  });

  constructor() {
    super();
    this.config = {
      entityType: 'customers',
      entityLabel: 'Customers',
      defaultPageSize: 10,
      defaultOrdering: '-created_at',
      enableBulkDelete: true,
      enableDelete: true,
    } as BaseListConfig<Customer>;
  }

  /**
   * Create the Observable that fetches a page of customers.
   */
  protected override createListLoader(
    params: ListRequestParams,
  ): Observable<PaginatedResponse<Customer>> {
    return this.customersService.list({
      page: params.page,
      pageSize: params.pageSize,
      query: params.query || undefined,
      ordering: params.ordering || undefined,
      status: this.statusFilter(),
    });
  }

  /**
   * Persist status filter in URL (omit when default 'active').
   */
  protected override getExtraUrlParams(): Record<string, string | null> {
    const status = this.statusFilter();
    return { status: status !== 'active' ? status : null };
  }

  /**
   * Restore status filter from URL query params.
   */
  protected override restoreExtraUrlParams(params: Record<string, string | undefined>): void {
    const status = params['status'];
    if (status === 'all' || status === 'active' || status === 'disabled') {
      this.statusFilter.set(status);
    }
  }

  /**
   * Handle status filter change
   */
  onStatusChange(value: string | string[]): void {
    if (typeof value === 'string') {
      this.statusFilter.set(value as 'all' | 'active' | 'disabled');
      this.page.set(1);
      this.updateUrl();
      this.reload();
    }
  }

  /**
   * Handle enter in search to focus table
   */
  onEnterSearch(): void {
    const table = this.dataTable();
    if (table) {
      table.focusFirstRowIfNone();
    }
  }

  /**
   * Toggle customer active status
   */
  onToggleActive(customer: Customer): void {
    this.customersService.toggleActive(customer.id).subscribe({
      next: () => {
        this.toast.success(`Customer ${customer.active ? 'disabled' : 'enabled'}`);
        this.reload();
      },
      error: () => {
        this.toast.error('Failed to update customer status');
      },
    });
  }

  /**
   * Delete single customer
   */
  onDelete(customer: Customer): void {
    if (!confirm(`Delete customer ${customer.fullNameWithCompany}? This cannot be undone.`)) {
      return;
    }

    this.customersService.deleteCustomer(customer.id).subscribe({
      next: () => {
        this.toast.success('Customer deleted');
        this.reload();
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete customer: ${message}` : 'Failed to delete customer',
        );
      },
    });
  }

  /**
   * Open bulk delete dialog
   */
  override openBulkDeleteDialog(): void {
    const query = this.query().trim();
    const mode = query ? 'selected' : 'all';
    const detailsText = query
      ? 'This will permanently remove all matching customer records, their applications, invoices, and associated data.'
      : 'This will permanently remove all customer records and their associated data from the database.';

    this.bulkDeleteContext.set({ query, status: this.statusFilter() });
    this.bulkDeleteData.set({
      entityLabel: 'Customers',
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
    const context = this.bulkDeleteContext();
    if (!context) {
      return;
    }

    this.customersService
      .bulkDeleteCustomers(context.query || undefined, context.status === 'active')
      .subscribe({
        next: (result) => {
          this.toast.success(`Deleted ${result.deletedCount} customer(s)`);
          this.bulkDeleteOpen.set(false);
          this.bulkDeleteData.set(null);
          this.bulkDeleteContext.set(null);
          this.reload();
        },
        error: (error) => {
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to delete customers: ${message}` : 'Failed to delete customers',
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
   * Get WhatsApp link
   */
  getWhatsAppHref(number: string | null): string | null {
    if (!number) return null;
    const digits = (number || '').replace(/\D/g, '');
    return `https://wa.me/${digits}`;
  }

  /**
   * Build navigation state for item actions
   */
  private navigationState(id: number): Record<string, unknown> {
    return {
      from: 'customers',
      focusId: id,
      searchQuery: this.query(),
      page: this.page(),
    };
  }
}
