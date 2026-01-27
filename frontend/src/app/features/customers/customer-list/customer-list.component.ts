import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { CustomersService, type CustomerListItem } from '@/core/services/customers.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import {
  DataTableComponent,
  type ColumnConfig,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { ExpiryBadgeComponent } from '@/shared/components/expiry-badge';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';

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
  ],
  templateUrl: './customer-list.component.html',
  styleUrls: ['./customer-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerListComponent implements OnInit {
  private customersService = inject(CustomersService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

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
  private readonly telephoneTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('telephoneTemplate');
  private readonly actionsTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: CustomerListItem; value: any; row: CustomerListItem }>
    >('actionsTemplate');

  readonly customers = signal<CustomerListItem[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(8);
  readonly totalItems = signal(0);
  readonly hideDisabled = signal(true);
  readonly ordering = signal<string | undefined>('-created_at');

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
      key: 'email',
      header: 'Email',
      sortable: true,
      sortKey: 'email',
      template: this.emailTemplate(),
    },
    {
      key: 'telephone',
      header: 'Telephone',
      template: this.telephoneTemplate(),
    },
    {
      key: 'actions',
      header: 'Actions',
      template: this.actionsTemplate(),
    },
  ]);

  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    this.loadCustomers();
  }

  onQueryChange(value: string): void {
    this.query.set(value.trim());
    this.page.set(1);
    this.loadCustomers();
  }

  onToggleHideDisabled(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.hideDisabled.set(checked);
    this.page.set(1);
    this.loadCustomers();
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
      error: () => {
        this.toast.error('Failed to delete customer');
      },
    });
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
        hideDisabled: this.hideDisabled(),
      })
      .subscribe({
        next: (response) => {
          this.customers.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
          this.isLoading.set(false);
        },
        error: () => {
          this.toast.error('Failed to load customers');
          this.isLoading.set(false);
        },
      });
  }
}
