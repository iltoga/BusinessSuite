import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { RouterLink } from '@angular/router';

import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { DocApplicationSerializerWithRelations } from '@/core/api/model/doc-application-serializer-with-relations';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeImports } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import {
  DataTableComponent,
  type ColumnConfig,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';

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
    ...ZardBadgeImports,
  ],
  templateUrl: './application-list.component.html',
  styleUrls: ['./application-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationListComponent implements OnInit {
  private service = inject(CustomerApplicationsService);
  private toast = inject(GlobalToastService);

  readonly items = signal<DocApplicationSerializerWithRelations[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly totalItems = signal(0);
  readonly ordering = signal<string | undefined>('-doc_date');

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
  private readonly actionsTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnActions');
  private readonly invoiceActionsTemplate =
    viewChild.required<
      TemplateRef<{ $implicit: DocApplicationSerializerWithRelations; value: any; row: any }>
    >('columnInvoiceActions');

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
    },
    { key: 'actions', header: 'Application Actions', template: this.actionsTemplate() },
    { key: 'invoiceActions', header: 'Invoice Actions', template: this.invoiceActionsTemplate() },
  ]);

  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  ngOnInit(): void {
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

  confirmDelete(row: DocApplicationSerializerWithRelations) {
    if (confirm(`Delete application #${row.id}? This action cannot be undone.`)) {
      this.service.customerApplicationsDestroy(row.id).subscribe({
        next: () => {
          this.toast.success('Application deleted');
          this.load();
        },
        error: () => {
          this.toast.error('Failed to delete application');
        },
      });
    }
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
        },
        error: () => {
          this.toast.error('Failed to load applications');
          this.isLoading.set(false);
        },
      });
  }
}
