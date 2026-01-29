import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { InvoicesService, type InvoiceList, type PaginatedInvoiceListList } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import {
  DataTableComponent,
  type ColumnConfig,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';

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
  ],
  templateUrl: './invoice-list.component.html',
  styleUrls: ['./invoice-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceListComponent implements OnInit {
  private invoicesApi = inject(InvoicesService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

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

  readonly invoices = signal<InvoiceList[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly totalItems = signal(0);
  readonly ordering = signal<string | undefined>('-invoice_date');
  readonly hidePaid = signal(false);

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
    { key: 'actions', header: 'Actions', template: this.actionsTemplate() },
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
    this.loadInvoices();
  }

  onQueryChange(value: string): void {
    this.query.set(value.trim());
    this.page.set(1);
    this.loadInvoices();
  }

  onToggleHidePaid(event: Event): void {
    const checked = (event.target as HTMLInputElement).checked;
    this.hidePaid.set(checked);
    this.page.set(1);
    this.loadInvoices();
  }

  onPageChange(page: number): void {
    this.page.set(page);
    this.loadInvoices();
  }

  onSortChange(sort: SortEvent): void {
    const ordering = sort.direction === 'desc' ? `-${sort.column}` : sort.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.loadInvoices();
  }

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

  private loadInvoices(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

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
          this.invoices.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
          this.isLoading.set(false);
        },
        error: () => {
          this.toast.error('Failed to load invoices');
          this.isLoading.set(false);
        },
      });
  }
}
