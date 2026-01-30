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

import { ProductsService, type PaginatedProductList, type Product } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import {
  BulkDeleteDialogComponent,
  type BulkDeleteDialogData,
} from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import {
  DataTableComponent,
  type ColumnConfig,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';

@Component({
  selector: 'app-product-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    DataTableComponent,
    SearchToolbarComponent,
    PaginationControlsComponent,
    ZardButtonComponent,
    ConfirmDialogComponent,
    ZardBadgeComponent,
    BulkDeleteDialogComponent,
  ],
  templateUrl: './product-list.component.html',
  styleUrls: ['./product-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductListComponent implements OnInit {
  private productsApi = inject(ProductsService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

  private readonly nameTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'nameTemplate',
    );
  private readonly descriptionTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'descriptionTemplate',
    );
  private readonly typeTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'typeTemplate',
    );
  private readonly priceTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'priceTemplate',
    );
  private readonly actionsTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'actionsTemplate',
    );

  readonly products = signal<Product[]>([]);
  readonly isLoading = signal(false);
  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly totalItems = signal(0);
  readonly ordering = signal<string | undefined>('name');
  readonly isSuperuser = this.authService.isSuperuser;

  readonly bulkDeleteOpen = signal(false);
  readonly bulkDeleteData = signal<BulkDeleteDialogData | null>(null);
  private readonly bulkDeleteQuery = signal<string>('');

  readonly confirmOpen = signal(false);
  readonly confirmMessage = signal('');
  readonly pendingDelete = signal<Product | null>(null);

  readonly bulkDeleteLabel = computed(() =>
    this.query().trim() ? 'Delete Selected Products' : 'Delete All Products',
  );

  readonly columns = computed<ColumnConfig<Product>[]>(() => [
    { key: 'code', header: 'Code', sortable: true, sortKey: 'code' },
    { key: 'name', header: 'Name', sortable: true, sortKey: 'name', template: this.nameTemplate() },
    { key: 'description', header: 'Description', template: this.descriptionTemplate() },
    {
      key: 'productType', // property name on the model (camelCase)
      header: 'Type',
      sortable: true,
      sortKey: 'product_type', // server uses snake_case for ordering
      template: this.typeTemplate(),
    },

    {
      key: 'basePrice', // property name on the model (camelCase)
      header: 'Base Price',
      sortable: true,
      sortKey: 'base_price', // server uses snake_case for ordering
      template: this.priceTemplate(),
    },
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
    this.loadProducts();
  }

  onQueryChange(value: string): void {
    this.query.set(value.trim());
    this.page.set(1);
    this.loadProducts();
  }

  onPageChange(page: number): void {
    this.page.set(page);
    this.loadProducts();
  }

  onSortChange(sort: SortEvent): void {
    const ordering = sort.direction === 'desc' ? `-${sort.column}` : sort.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.loadProducts();
  }

  requestDelete(product: Product): void {
    if (!this.isSuperuser()) {
      return;
    }
    this.productsApi.productsCanDeleteRetrieve(product.id).subscribe({
      next: (result) => {
        const payload = result as unknown as { can_delete: boolean; message?: string | null };
        if (!payload.can_delete) {
          this.toast.error(payload.message ?? 'Product cannot be deleted.');
          return;
        }
        this.pendingDelete.set(product);
        this.confirmMessage.set(
          payload.message ??
            `Delete product ${product.code} - ${product.name}? This cannot be undone.`,
        );
        this.confirmOpen.set(true);
      },
      error: () => {
        this.toast.error('Failed to validate delete request');
      },
    });
  }

  confirmDelete(): void {
    const product = this.pendingDelete();
    if (!product) {
      return;
    }
    this.productsApi.productsDestroy(product.id).subscribe({
      next: () => {
        this.toast.success('Product deleted');
        this.confirmOpen.set(false);
        this.pendingDelete.set(null);
        this.loadProducts();
      },
      error: () => {
        this.toast.error('Failed to delete product');
      },
    });
  }

  cancelDelete(): void {
    this.confirmOpen.set(false);
    this.pendingDelete.set(null);
  }

  openBulkDeleteDialog(): void {
    const query = this.query().trim();
    const mode = query ? 'selected' : 'all';
    const detailsText = query
      ? 'This will permanently remove all matching product records and their associated tasks from the database.'
      : 'This will permanently remove all product records and their associated tasks from the database.';

    this.bulkDeleteQuery.set(query);
    this.bulkDeleteData.set({
      entityLabel: 'Products',
      totalCount: this.totalItems(),
      query: query || null,
      mode,
      detailsText,
    });
    this.bulkDeleteOpen.set(true);
  }

  onBulkDeleteConfirmed(): void {
    const query = this.bulkDeleteQuery();

    this.productsApi.productsBulkDeleteCreate({ searchQuery: query || '' } as any).subscribe({
      next: (response) => {
        const payload = response as { deletedCount?: number; deleted_count?: number };
        const count = payload.deletedCount ?? payload.deleted_count ?? 0;
        this.toast.success(`Deleted ${count} product(s)`);
        this.bulkDeleteOpen.set(false);
        this.bulkDeleteData.set(null);
        this.bulkDeleteQuery.set('');
        this.loadProducts();
      },
      error: () => {
        this.toast.error('Failed to delete products');
      },
    });
  }

  onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.bulkDeleteQuery.set('');
  }

  productTypeLabel(type?: string | null): string {
    if (type === 'visa') return 'Visa';
    if (type === 'other') return 'Other';
    return type ?? '—';
  }

  formatCurrency(value?: string | null): string {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (Number.isNaN(n)) return String(value ?? '—');
    // Format as Indonesian Rupiah without decimals
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      maximumFractionDigits: 0,
    }).format(n);
  }

  private loadProducts(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    this.isLoading.set(true);
    const ordering = this.ordering();

    this.productsApi
      .productsList(ordering ?? undefined, this.page(), this.pageSize(), this.query() || undefined)
      .subscribe({
        next: (response: PaginatedProductList) => {
          this.products.set(response.results ?? []);
          this.totalItems.set(response.count ?? 0);
          this.isLoading.set(false);
        },
        error: () => {
          this.toast.error('Failed to load products');
          this.isLoading.set(false);
        },
      });
  }
}
