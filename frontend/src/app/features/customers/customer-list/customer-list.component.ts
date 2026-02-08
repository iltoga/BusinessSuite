import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  HostListener,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';

import { AuthService } from '@/core/services/auth.service';
import { CustomersService, type CustomerListItem } from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge/badge.component';
import {
  BulkDeleteDialogComponent,
  type BulkDeleteDialogData,
} from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import {
  DataTableComponent,
  type ColumnConfig,
  type DataTableAction,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { ExpiryBadgeComponent } from '@/shared/components/expiry-badge';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardSelectImports } from '@/shared/components/select';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

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
    BulkDeleteDialogComponent,
    ...ZardSelectImports,
    ZardBadgeComponent,
  ],
  templateUrl: './customer-list.component.html',
  styleUrls: ['./customer-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerListComponent implements OnInit {
  private customersService = inject(CustomersService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);
  private router = inject(Router);

  /** Access the data table for focus management */
  private readonly dataTable = viewChild.required(DataTableComponent);

  private readonly customerTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('customerTemplate');
  private readonly passportTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('passportTemplate');
  private readonly emailTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('emailTemplate');
  private readonly whatsappTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('whatsappTemplate');
  private readonly nationalityTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('nationalityTemplate');
  private readonly createdAtTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('createdAtTemplate');
  readonly customers = signal<CustomerListItem[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(8);
  readonly totalItems = signal(0);
  readonly statusFilter = signal<'all' | 'active' | 'disabled'>('active');
  readonly ordering = signal<string | undefined>('-created_at');
  readonly isSuperuser = this.authService.isSuperuser;

  readonly bulkDeleteOpen = signal(false);
  readonly bulkDeleteData = signal<BulkDeleteDialogData | null>(null);
  private readonly bulkDeleteContext = signal<{
    query: string;
    status: 'all' | 'active' | 'disabled';
  } | null>(null);

  readonly bulkDeleteLabel = computed(() =>
    this.query().trim() ? 'Delete Selected Customers' : 'Delete All Customers',
  );

  readonly columns = computed<ColumnConfig[]>(() => [
    {
      key: 'fullNameWithCompany',
      header: 'Customer',
      sortable: true,
      sortKey: 'last_name',
      template: this.customerTemplate(),
    },
    {
      key: 'passportNumber',
      header: 'Passport',
      subtitle: 'Valid till',
      template: this.passportTemplate(),
    },
    {
      key: 'nationalityName',
      header: 'Nationality',
      sortable: true,
      sortKey: 'nationality__country',
      template: this.nationalityTemplate(),
    },
    {
      key: 'email',
      header: 'Email',
      sortable: true,
      sortKey: 'email',
      template: this.emailTemplate(),
    },
    {
      key: 'whatsapp',
      header: 'WhatsApp',
      template: this.whatsappTemplate(),
    },
    {
      key: 'createdAt',
      header: 'Added/Updated',
      sortable: true,
      sortKey: 'created_at',
      template: this.createdAtTemplate(),
    },
    {
      key: 'actions',
      header: 'Actions',
    },
  ]);

  readonly actions = computed<DataTableAction<CustomerListItem>[]>(() => {
    const actions: DataTableAction<CustomerListItem>[] = [
      {
        label: 'View Detail',
        icon: 'eye',
        variant: 'default',
        action: (item) =>
          this.router.navigate(['/customers', item.id], {
            state: { from: 'customers', focusId: item.id, searchQuery: this.query() },
          }),
      },
      {
        label: 'Edit',
        icon: 'settings',
        variant: 'warning',
        action: (item) =>
          this.router.navigate(['/customers', item.id, 'edit'], {
            state: { from: 'customers', focusId: item.id, searchQuery: this.query() },
          }),
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
            state: { from: 'customers', focusId: item.id, searchQuery: this.query() },
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

  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  // When navigating back to the list we may want to focus a specific id or the table
  private readonly focusTableOnInit = signal(false);
  private readonly focusIdOnInit = signal<number | null>(null);

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    // Only trigger if no input is focused
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    // Shift+N for New Customer
    if (event.key === 'N' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.router.navigate(['/customers', 'new'], {
        state: { from: 'customers', searchQuery: this.query() },
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
    this.loadCustomers();
  }

  onQueryChange(value: string): void {
    const trimmed = value.trim();
    if (this.query() === trimmed) return;
    this.query.set(trimmed);
    this.page.set(1);
    this.loadCustomers();
  }

  onStatusChange(value: string | string[]): void {
    if (typeof value === 'string') {
      this.statusFilter.set(value as 'all' | 'active' | 'disabled');
      this.page.set(1);
      this.loadCustomers();
    }
  }

  onPageChange(page: number): void {
    this.page.set(page);
    this.loadCustomers();
  }

  onSortChange(sort: SortEvent): void {
    const ordering = sort.direction === 'desc' ? `-${sort.column}` : sort.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.loadCustomers();
  }

  onEnterSearch(): void {
    const table = this.dataTable();
    if (table) {
      table.focusFirstRowIfNone();
    }
  }

  onToggleActive(customer: CustomerListItem): void {
    this.customersService.toggleActive(customer.id).subscribe({
      next: () => {
        this.toast.success(`Customer ${customer.active ? 'disabled' : 'enabled'}`);
        this.loadCustomers();
      },
      error: () => {
        this.toast.error('Failed to update customer status');
      },
    });
  }

  onDelete(customer: CustomerListItem): void {
    if (!confirm(`Delete customer ${customer.fullNameWithCompany}? This cannot be undone.`)) {
      return;
    }

    this.customersService.deleteCustomer(customer.id).subscribe({
      next: () => {
        this.toast.success('Customer deleted');
        this.loadCustomers();
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete customer: ${message}` : 'Failed to delete customer',
        );
      },
    });
  }

  openBulkDeleteDialog(): void {
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
          this.loadCustomers();
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

  onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.bulkDeleteContext.set(null);
  }

  getWhatsAppHref(number: string | null): string | null {
    if (!number) return null;
    const digits = (number || '').replace(/\D/g, '');
    return `https://wa.me/${digits}`;
  }

  private loadCustomers(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
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
          this.customers.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
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
          this.toast.error('Failed to load customers');
          this.isLoading.set(false);
        },
      });
  }
}
