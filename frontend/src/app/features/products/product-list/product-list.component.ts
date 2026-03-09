import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  PLATFORM_ID,
  signal,
  viewChild,
  type TemplateRef,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { Router, RouterLink } from '@angular/router';
import { Subject, catchError, of, switchMap, takeWhile } from 'rxjs';

import { ProductsService, type Product } from '@/core/api';
import { JobService } from '@/core/services/job.service';
import { ConfigService } from '@/core/services/config.service';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
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
import { ZardIconComponent } from '@/shared/components/icon';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import {
  ProductDeleteDialogComponent,
  type ProductDeleteDialogResult,
  type ProductDeletePreviewData,
} from '@/shared/components/product-delete-dialog/product-delete-dialog.component';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { ContextHelpDirective } from '@/shared/directives';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { downloadBlob } from '@/shared/utils/file-download';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Product list component
 * 
 * Extends BaseListComponent to inherit common list patterns:
 * - Keyboard shortcuts (N for new, B/Left for back)
 * - Navigation state restoration
 * - Pagination, sorting, search
 * - Focus management
 * - Bulk delete support
 */
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
    ZardCardComponent,
    ZardIconComponent,
    ProductDeleteDialogComponent,
    ZardBadgeComponent,
    BulkDeleteDialogComponent,
    ...ZardTooltipImports,
    AppDatePipe,
  ],
  templateUrl: './product-list.component.html',
  styleUrls: ['./product-list.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ProductListComponent extends BaseListComponent<Product> {
  private readonly productsApi = inject(ProductsService);
  private readonly productImportExportApi = inject(ProductImportExportService);
  private readonly jobService = inject(JobService);
  private readonly configService = inject(ConfigService);
  private readonly loadProductsTrigger$ = new Subject<void>();

  // Expose products for template compatibility
  get products() {
    return this.items;
  }

  // Product-specific state
  readonly includeDeprecated = signal(false);
  readonly exportInProgress = signal(false);
  readonly exportProgress = signal<number | null>(null);
  readonly importInProgress = signal(false);
  readonly importProgress = signal<number | null>(null);
  readonly basePricesVisible = signal(false);

  // Product delete dialog state
  readonly productDeleteOpen = signal(false);
  readonly productDeleteData = signal<ProductDeletePreviewData | null>(null);
  readonly pendingDelete = signal<Product | null>(null);

  // Template references
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
  private readonly basePriceHeaderTemplate =
    viewChild.required<TemplateRef<{ column: ColumnConfig<Product> }>>('basePriceHeaderTemplate');
  private readonly priceTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'priceTemplate',
    );
  private readonly retailPriceTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'retailPriceTemplate',
    );
  private readonly profitTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'profitTemplate',
    );
  private readonly createdAtTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'createdAtTemplate',
    );
  private readonly importFileInput = viewChild<ElementRef<HTMLInputElement>>('importFileInput');

  // Product-specific bulk delete query
  private readonly productBulkDeleteQuery = signal<string>('');

  // Columns configuration
  readonly columns = computed<ColumnConfig<Product>[]>(() => [
    { key: 'code', header: 'Code', sortable: true, sortKey: 'code' },
    { key: 'name', header: 'Name', sortable: true, sortKey: 'name', template: this.nameTemplate() },
    { key: 'description', header: 'Description', template: this.descriptionTemplate() },
    {
      key: 'productType',
      header: 'Type',
      sortable: true,
      sortKey: 'product_type',
      template: this.typeTemplate(),
    },
    {
      key: 'basePrice',
      header: 'Base Price',
      sortable: true,
      sortKey: 'base_price',
      headerActionTemplate: this.basePriceHeaderTemplate(),
      template: this.priceTemplate(),
    },
    {
      key: 'retailPrice',
      header: 'Retail Price',
      sortable: true,
      sortKey: 'retail_price',
      template: this.retailPriceTemplate(),
    },
    {
      key: 'unitProfit',
      header: 'Unit Profit',
      template: this.profitTemplate(),
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

  // Actions configuration
  override readonly actions = computed<DataTableAction<Product>[]>(() => [
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
      action: (item) => this.requestDelete(item),
    },
  ]);

  // Row class for deprecated products
  readonly rowClassFn = (row: Product): string => (row.deprecated ? 'opacity-60' : '');

  constructor() {
    super();
    this.config = {
      entityType: 'products',
      entityLabel: 'Products',
      defaultPageSize: 10,
      defaultOrdering: 'name',
      enableBulkDelete: true,
      enableDelete: true,
    } as BaseListConfig<Product>;

    // Setup load trigger with rxjs pattern
    this.loadProductsTrigger$
      .pipe(
        switchMap(() => {
          this.isLoading.set(true);
          const ordering = this.ordering();
          const search = this.query().trim();

          return this.productsApi
            .productsList(
              undefined,
              !this.includeDeprecated(),
              ordering,
              this.page(),
              this.pageSize(),
              search || undefined,
            )
            .pipe(
              catchError(() => {
                this.toast.error('Failed to load products');
                return of(null);
              }),
            );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((response) => {
        if (!response) {
          this.isLoading.set(false);
          return;
        }

        this.items.set(response.results ?? []);
        this.totalItems.set(response.count ?? 0);
        this.isLoading.set(false);
        this.focusAfterLoad();
      });
  }

  /**
   * Load products from service
   */
  protected override loadItems(): void {
    if (!this.isBrowser) return;
    this.loadProductsTrigger$.next();
  }

  /**
   * Handle toggle include deprecated
   */
  onToggleIncludeDeprecated(value: boolean): void {
    this.includeDeprecated.set(value);
    this.page.set(1);
    this.loadItems();
  }

  /**
   * Request delete for a product
   */
  requestDelete(product: Product): void {
    if (!this.isSuperuser()) {
      return;
    }
    this.pendingDelete.set(product);
    this.productsApi.productsDeletePreviewRetrieve(product.id).subscribe({
      next: (result) => {
        this.productDeleteData.set(this.mapProductDeletePreview(result, product));
        this.productDeleteOpen.set(true);
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to load delete preview: ${message}` : 'Failed to load delete preview',
        );
        this.pendingDelete.set(null);
      },
    });
  }

  /**
   * Handle product delete confirmation
   */
  onProductDeleteConfirmed(result: ProductDeleteDialogResult): void {
    const product = this.pendingDelete();
    if (!product) {
      return;
    }
    const deleteRequest = result.forceDelete
      ? this.productsApi.productsForceDeleteCreate(product.id, { forceDeleteConfirmed: true } as any)
      : this.productsApi.productsDestroy(product.id);

    deleteRequest.subscribe({
      next: () => {
        this.toast.success(result.forceDelete ? 'Product force deleted' : 'Product deleted');
        this.resetProductDeleteDialog();
        this.loadItems();
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete product: ${message}` : 'Failed to delete product',
        );
        this.resetProductDeleteDialog();
      },
    });
  }

  /**
   * Handle product delete cancellation
   */
  onProductDeleteCancelled(): void {
    this.resetProductDeleteDialog();
  }

  /**
   * Open bulk delete dialog
   */
  override openBulkDeleteDialog(): void {
    const query = this.query().trim();
    const mode = query ? 'selected' : 'all';
    const detailsText = query
      ? 'This will permanently remove all matching product records and their associated tasks from the database.'
      : 'This will permanently remove all product records and their associated tasks from the database.';

    this.productBulkDeleteQuery.set(query);
    this.bulkDeleteData.set({
      entityLabel: 'Products',
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
    const query = this.productBulkDeleteQuery();

    this.productsApi.productsBulkDeleteCreate({ searchQuery: query || '' } as any).subscribe({
      next: (response) => {
        const payload = response as { deletedCount?: number; deleted_count?: number };
        const count = payload.deletedCount ?? payload.deleted_count ?? 0;
        this.toast.success(`Deleted ${count} product(s)`);
        this.bulkDeleteOpen.set(false);
        this.bulkDeleteData.set(null);
        this.productBulkDeleteQuery.set('');
        this.loadItems();
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

  /**
   * Handle bulk delete cancellation
   */
  override onBulkDeleteCancelled(): void {
    this.bulkDeleteOpen.set(false);
    this.bulkDeleteData.set(null);
    this.productBulkDeleteQuery.set('');
  }

  /**
   * Start product export
   */
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

  /**
   * Open import file picker
   */
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

  /**
   * Handle import file selection
   */
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

  /**
   * Get product type label
   */
  productTypeLabel(type?: string | null): string {
    if (type === 'visa') return 'Visa';
    if (type === 'other') return 'Other';
    return type ?? '—';
  }

  /**
   * Toggle base price visibility
   */
  toggleBasePriceVisibility(event?: Event): void {
    event?.stopPropagation();
    this.basePricesVisible.update((visible) => !visible);
  }

  /**
   * Resolve currency for a product
   */
  resolveCurrency(row?: Product | null): string {
    const configured = String(this.configService.settings.baseCurrency ?? 'IDR')
      .trim()
      .toUpperCase();
    const currency = String(((row as any)?.currency ?? configured) || 'IDR')
      .trim()
      .toUpperCase();
    if (!currency || currency.length < 2 || currency.length > 3 || !/^[A-Z]+$/.test(currency)) {
      return 'IDR';
    }
    return currency;
  }

  /**
   * Format currency value
   */
  formatCurrency(value?: string | number | null, currencyCode?: string): string {
    if (value === null || value === undefined || value === '') return '—';
    const n = Number(value);
    if (Number.isNaN(n)) return String(value ?? '—');
    const currency = currencyCode ?? this.resolveCurrency();
    try {
      return new Intl.NumberFormat('en-US', {
        style: 'currency',
        currency,
        maximumFractionDigits: 2,
      }).format(n);
    } catch {
      return `${currency} ${n.toLocaleString('en-US')}`;
    }
  }

  /**
   * Format base price with visibility toggle
   */
  formatBasePrice(value?: string | number | null, row?: Product): string {
    if (!this.basePricesVisible()) {
      return '****';
    }
    return this.formatCurrency(value, this.resolveCurrency(row));
  }

  /**
   * Get retail price value
   */
  retailPriceValue(row: Product): string | number | null {
    const retail = (row as any).retailPrice ?? (row as any).retail_price;
    const base = (row as any).basePrice ?? (row as any).base_price;
    return retail ?? base ?? null;
  }

  /**
   * Calculate unit profit
   */
  unitProfitValue(row: Product): number {
    const retail = Number(this.retailPriceValue(row) ?? 0);
    const base = Number((row as any).basePrice ?? (row as any).base_price ?? 0);
    if (Number.isNaN(retail) || Number.isNaN(base)) {
      return 0;
    }
    return retail - base;
  }

  /**
   * Watch export job progress
   */
  private watchExportJob(jobId: string): void {
    this.jobService.watchJob(jobId).subscribe({
      next: (job) => {
        this.exportProgress.set(Number(job.progress ?? 0));

        if (job.status === 'completed') {
          this.downloadExport(jobId);
          this.exportInProgress.set(false);
          this.exportProgress.set(null);
        } else if (job.status === 'failed') {
          this.toast.error(job.errorMessage || 'Product export failed');
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

  /**
   * Watch import job progress
   */
  private watchImportJob(jobId: string): void {
    this.jobService.watchJob(jobId).subscribe({
      next: (job) => {
        this.importProgress.set(Number(job.progress ?? 0));
        if (job.status === 'completed') {
          this.toast.success('Import completed successfully');
          this.importInProgress.set(false);
          this.importProgress.set(null);
          this.loadItems();
        } else if (job.status === 'failed') {
          this.toast.error(job.errorMessage || 'Product import failed');
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

  /**
   * Download export file
   */
  private downloadExport(jobId: string): void {
    this.productImportExportApi.downloadExport(jobId).subscribe({
      next: (response) => {
        const blob = response.body;
        if (blob) {
          downloadBlob(blob, `products-export-${jobId}.xlsx`);
          this.toast.success('Export completed successfully');
        }
      },
      error: () => {
        this.toast.error('Failed to download export file');
      },
    });
  }

  /**
   * Reset product delete dialog
   */
  private resetProductDeleteDialog(): void {
    this.productDeleteOpen.set(false);
    this.productDeleteData.set(null);
    this.pendingDelete.set(null);
  }

  /**
   * Map product delete preview response
   */
  private mapProductDeletePreview(response: unknown, product: Product): ProductDeletePreviewData {
    const payload: any = response ?? {};
    const relatedCounts: any = payload.relatedCounts ?? payload.related_counts ?? {};
    const relatedRecords: any = payload.relatedRecords ?? payload.related_records ?? {};
    const relatedRecordsTruncated: any =
      payload.relatedRecordsTruncated ?? payload.related_records_truncated ?? {};

    const taskRecords = this.asArray<any>(relatedRecords.tasks).map((task: any) => ({
      id: this.asNumber(task?.id),
      step: this.asNumber(task?.step),
      name: String(task?.name ?? ''),
    }));

    const applicationRecords = this.asArray<any>(relatedRecords.applications).map(
      (application: any) => ({
        id: this.asNumber(application?.id),
        customerName: String(application?.customerName ?? application?.customer_name ?? '—'),
        status: String(application?.status ?? ''),
        statusDisplay: String(application?.statusDisplay ?? application?.status_display ?? ''),
        docDate: application?.docDate ?? application?.doc_date ?? null,
        dueDate: application?.dueDate ?? application?.due_date ?? null,
        workflowCount: this.asNumber(application?.workflowCount ?? application?.workflow_count),
        documentCount: this.asNumber(application?.documentCount ?? application?.document_count),
        invoiceLineCount: this.asNumber(
          application?.invoiceLineCount ?? application?.invoice_line_count,
        ),
      }),
    );

    const invoiceLineRecords = this.asArray<any>(
      relatedRecords.invoiceApplications ?? relatedRecords.invoice_applications,
    ).map((invoiceLine: any) => ({
      id: this.asNumber(invoiceLine?.id),
      invoiceId: this.asNumber(invoiceLine?.invoiceId ?? invoiceLine?.invoice_id),
      invoiceNoDisplay: String(invoiceLine?.invoiceNoDisplay ?? invoiceLine?.invoice_no_display ?? ''),
      invoiceStatus: String(invoiceLine?.invoiceStatus ?? invoiceLine?.invoice_status ?? ''),
      customerApplicationId: this.asNullableNumber(
        invoiceLine?.customerApplicationId ?? invoiceLine?.customer_application_id,
      ),
      customerName: String(invoiceLine?.customerName ?? invoiceLine?.customer_name ?? '—'),
      amount: invoiceLine?.amount ?? '0',
      status: String(invoiceLine?.status ?? ''),
      statusDisplay: String(invoiceLine?.statusDisplay ?? invoiceLine?.status_display ?? ''),
      paymentCount: this.asNumber(invoiceLine?.paymentCount ?? invoiceLine?.payment_count),
    }));

    return {
      productId: this.asNumber(payload.productId ?? payload.product_id ?? product.id),
      productCode: String(payload.productCode ?? payload.product_code ?? product.code ?? ''),
      productName: String(payload.productName ?? payload.product_name ?? product.name ?? ''),
      canDelete: Boolean(payload.canDelete ?? payload.can_delete ?? true),
      requiresForceDelete: Boolean(
        payload.requiresForceDelete ?? payload.requires_force_delete ?? false,
      ),
      message: payload.message ?? null,
      relatedCounts: {
        tasks: this.asNumber(relatedCounts.tasks),
        applications: this.asNumber(relatedCounts.applications),
        workflows: this.asNumber(relatedCounts.workflows),
        documents: this.asNumber(relatedCounts.documents),
        invoiceApplications: this.asNumber(
          relatedCounts.invoiceApplications ?? relatedCounts.invoice_applications,
        ),
        invoices: this.asNumber(relatedCounts.invoices),
        payments: this.asNumber(relatedCounts.payments),
      },
      relatedRecords: {
        tasks: taskRecords,
        applications: applicationRecords,
        invoiceApplications: invoiceLineRecords,
      },
      relatedRecordsTruncated: {
        tasks: Boolean(relatedRecordsTruncated.tasks),
        applications: Boolean(relatedRecordsTruncated.applications),
        invoiceApplications: Boolean(
          relatedRecordsTruncated.invoiceApplications ??
            relatedRecordsTruncated.invoice_applications,
        ),
      },
      recordLimit: this.asNullableNumber(payload.recordLimit ?? payload.record_limit) ?? undefined,
    };
  }

  /**
   * Convert value to array
   */
  private asArray<T>(value: unknown): T[] {
    return Array.isArray(value) ? (value as T[]) : [];
  }

  /**
   * Convert value to number
   */
  private asNumber(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  /**
   * Convert value to nullable number
   */
  private asNullableNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
}
