import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  HostListener,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  type OnInit,
  type TemplateRef,
} from '@angular/core';
import { Router, RouterLink } from '@angular/router';
import { catchError, Observable, takeWhile } from 'rxjs';

import { ProductsService, type PaginatedProductList, type Product } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
import { SseService } from '@/core/services/sse.service';
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
  type DataTableAction,
  type SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { ContextHelpDirective } from '@/shared/directives';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { downloadBlob } from '@/shared/utils/file-download';

@Component({
  selector: 'app-product-list',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    DataTableComponent,
    SearchToolbarComponent,
    PaginationControlsComponent,
    ContextHelpDirective,
    ZardButtonComponent,
    ConfirmDialogComponent,
    ZardBadgeComponent,
    BulkDeleteDialogComponent,
    ...ZardTooltipImports,
    AppDatePipe,
  ],
  templateUrl: './product-list.component.html',
  styleUrls: ['./product-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductListComponent implements OnInit {
  private productsApi = inject(ProductsService);
  private productImportExportApi = inject(ProductImportExportService);
  private sseService = inject(SseService);
  private authService = inject(AuthService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);
  private router = inject(Router);

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
  private readonly createdAtTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'createdAtTemplate',
    );
  private readonly importFileInput = viewChild<ElementRef<HTMLInputElement>>('importFileInput');

  // Access the data table for focus management
  private readonly dataTable = viewChild.required(DataTableComponent);

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
  readonly exportInProgress = signal(false);
  readonly exportProgress = signal<number | null>(null);
  readonly importInProgress = signal(false);
  readonly importProgress = signal<number | null>(null);

  // When navigating back to the list we may want to focus a specific id or the table
  private readonly focusTableOnInit = signal(false);
  private readonly focusIdOnInit = signal<number | null>(null);

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
    {
      key: 'createdAt',
      header: 'Added/Updated',
      sortable: true,
      sortKey: 'created_at',
      template: this.createdAtTemplate(),
    },
    { key: 'actions', header: 'Actions' },
  ]);

  readonly actions = computed<DataTableAction<Product>[]>(() => [
    {
      label: 'View',
      icon: 'eye',
      variant: 'default',
      action: (item) =>
        this.router.navigate(['/products', item.id], {
          state: { from: 'products', focusId: item.id, searchQuery: this.query() },
        }),
    },
    {
      label: 'Edit',
      icon: 'settings',
      variant: 'warning',
      action: (item) =>
        this.router.navigate(['/products', item.id, 'edit'], {
          state: { from: 'products', focusId: item.id, searchQuery: this.query() },
        }),
    },
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      isVisible: () => this.isSuperuser(),
      action: (item) => this.requestDelete(item),
    },
  ]);

  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement as HTMLElement | null;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement && activeElement.isContentEditable);

    if (isInput) return;

    // Shift+N for New Product
    if (event.key === 'N' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.router.navigate(['/products', 'new'], {
        state: { from: 'products', searchQuery: this.query() },
      });
    }
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const st = (window as any).history.state || {};
    this.focusTableOnInit.set(Boolean(st.focusTable));
    this.focusIdOnInit.set(st.focusId ? Number(st.focusId) : null);
    if (st.searchQuery) {
      this.query.set(String(st.searchQuery));
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
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete product: ${message}` : 'Failed to delete product',
        );
        this.confirmOpen.set(false);
        this.pendingDelete.set(null);
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
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete products: ${message}` : 'Failed to delete products',
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

  startExport(): void {
    if (this.exportInProgress()) {
      return;
    }
    this.exportInProgress.set(true);
    this.exportProgress.set(0);

    this.productImportExportApi.startExport(this.query().trim() || undefined).subscribe({
      next: (response) => {
        const jobId = (response as any)?.job_id ?? (response as any)?.jobId;
        if (!jobId) {
          this.toast.error('Export job was started but no job id was returned');
          this.exportInProgress.set(false);
          this.exportProgress.set(null);
          return;
        }
        this.watchExportJob(String(jobId));
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(message ? `Failed to start export: ${message}` : 'Failed to start export');
        this.exportInProgress.set(false);
        this.exportProgress.set(null);
      },
    });
  }

  openImportPicker(): void {
    if (this.importInProgress()) {
      return;
    }
    const input = this.importFileInput()?.nativeElement;
    if (!input) {
      return;
    }
    input.value = '';
    input.click();
  }

  onImportFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement | null;
    const file = input?.files?.[0];
    if (!file) {
      return;
    }

    const name = file.name.toLowerCase();
    if (!name.endsWith('.xlsx')) {
      this.toast.error('Only .xlsx files are supported');
      return;
    }

    this.importInProgress.set(true);
    this.importProgress.set(0);

    this.productImportExportApi.startImport(file).subscribe({
      next: (response) => {
        const jobId = (response as any)?.job_id ?? (response as any)?.jobId;
        if (!jobId) {
          this.toast.error('Import job was started but no job id was returned');
          this.importInProgress.set(false);
          this.importProgress.set(null);
          return;
        }
        this.watchImportJob(String(jobId));
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(message ? `Failed to start import: ${message}` : 'Failed to start import');
        this.importInProgress.set(false);
        this.importProgress.set(null);
      },
    });
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

  private watchExportJob(jobId: string): void {
    this.watchJob(jobId).subscribe({
      next: (job: any) => {
        this.exportProgress.set(Number(job?.progress ?? 0));

        if (job?.status === 'completed') {
          this.downloadExport(jobId);
          this.exportInProgress.set(false);
          this.exportProgress.set(null);
        } else if (job?.status === 'failed') {
          this.toast.error(job?.errorMessage || job?.error_message || 'Product export failed');
          this.exportInProgress.set(false);
          this.exportProgress.set(null);
        }
      },
      error: () => {
        this.toast.error('Failed to track export progress');
        this.exportInProgress.set(false);
        this.exportProgress.set(null);
      },
    });
  }

  private watchImportJob(jobId: string): void {
    this.watchJob(jobId).subscribe({
      next: (job: any) => {
        this.importProgress.set(Number(job?.progress ?? 0));
        if (job?.status === 'completed') {
          const result = (job?.result ?? {}) as Record<string, unknown>;
          const created = Number(result['created'] ?? 0);
          const updated = Number(result['updated'] ?? 0);
          const errors = Number(result['errors'] ?? 0);
          this.toast.success(
            `Import completed: ${created} created, ${updated} updated, ${errors} error(s).`,
          );
          this.importInProgress.set(false);
          this.importProgress.set(null);
          this.page.set(1);
          this.loadProducts();
        } else if (job?.status === 'failed') {
          this.toast.error(job?.errorMessage || job?.error_message || 'Product import failed');
          this.importInProgress.set(false);
          this.importProgress.set(null);
        }
      },
      error: () => {
        this.toast.error('Failed to track import progress');
        this.importInProgress.set(false);
        this.importProgress.set(null);
      },
    });
  }

  private downloadExport(jobId: string): void {
    this.productImportExportApi.downloadExport(jobId).subscribe({
      next: (response) => {
        const filename = this.resolveFilename(response) || 'products_export.xlsx';
        downloadBlob(response.body ?? new Blob(), filename);
        this.toast.success('Product export ready');
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(message ? `Failed to download export: ${message}` : 'Failed to download export');
      },
    });
  }

  private resolveFilename(response: { headers?: { get(name: string): string | null } }): string | null {
    const contentDisposition = response.headers?.get('content-disposition');
    if (!contentDisposition) return null;
    const filenameStarMatch = contentDisposition.match(/filename\*=UTF-8''([^;]+)/i);
    if (filenameStarMatch?.[1]) {
      return decodeURIComponent(filenameStarMatch[1]);
    }
    const filenameMatch = contentDisposition.match(/filename="?([^"]+)"?/i);
    return filenameMatch?.[1] ?? null;
  }

  private watchJob(jobId: string): Observable<any> {
    return this.sseService.connect<any>(`/api/async-jobs/status/${jobId}/`).pipe(
      catchError(() => this.productImportExportApi.pollJob(jobId)),
      takeWhile((job) => job?.status !== 'completed' && job?.status !== 'failed', true),
    );
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
          this.toast.error('Failed to load products');
          this.isLoading.set(false);
        },
      });
  }
}
