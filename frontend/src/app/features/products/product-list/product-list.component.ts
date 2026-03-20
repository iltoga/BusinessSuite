import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  ElementRef,
  inject,
  signal,
  viewChild,
  type TemplateRef,
} from '@angular/core';

import { RouterLink } from '@angular/router';
import { firstValueFrom, forkJoin, map, type Observable } from 'rxjs';

import { ProductsService, type AsyncJob, type Product } from '@/core/api';
import { ConfigService } from '@/core/services/config.service';
import { JobService } from '@/core/services/job.service';
import { ProductImportExportService } from '@/core/services/product-import-export.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { BulkDeleteDialogComponent } from '@/shared/components/bulk-delete-dialog/bulk-delete-dialog.component';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import {
  DataTableComponent,
  type ColumnConfig,
  type ColumnFilterChangeEvent,
  type ColumnFilterOption,
  type DataTableAction,
} from '@/shared/components/data-table/data-table.component';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import {
  ProductDeleteDialogComponent,
  type ProductDeleteDialogResult,
  type ProductDeletePreviewData,
} from '@/shared/components/product-delete-dialog/product-delete-dialog.component';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import {
  BaseListComponent,
  BaseListConfig,
  type ListRequestParams,
  type PaginatedResponse,
} from '@/shared/core/base-list.component';
import { ContextHelpDirective } from '@/shared/directives';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractJobId } from '@/core/utils/async-job-contract';
import { downloadBlob } from '@/shared/utils/file-download';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import {
  openPdfPrintPreview,
  openPendingPdfPrintPreviewWindow,
} from '@/shared/utils/pdf-print-preview';

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

  // Expose products for template compatibility
  get products() {
    return this.items;
  }

  // Product-specific state
  readonly exportInProgress = signal(false);
  readonly exportProgress = signal<number | null>(null);
  readonly importInProgress = signal(false);
  readonly importProgress = signal<number | null>(null);
  readonly printInProgress = signal(false);

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
  private readonly categoryTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'categoryTemplate',
    );
  private readonly deprecatedTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'deprecatedTemplate',
    );
  private readonly retailPriceTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'retailPriceTemplate',
    );
  private readonly createdAtTemplate =
    viewChild.required<TemplateRef<{ $implicit: Product; value: any; row: Product }>>(
      'createdAtTemplate',
    );
  private readonly importFileInput = viewChild<ElementRef<HTMLInputElement>>('importFileInput');

  // Product-specific bulk delete query
  private readonly productBulkDeleteQuery = signal<string>('');
  readonly columnFilters = signal<Record<string, string[]>>({
    deprecated: ['active'],
    productCategoryName: [],
  });

  readonly deprecatedFilterOptions: ColumnFilterOption[] = [
    { value: 'active', label: 'Not deprecated' },
    { value: 'deprecated', label: 'Deprecated' },
  ];
  readonly categoryFilterOptions = signal<ColumnFilterOption[]>([]);

  // Columns configuration
  readonly columns = computed<ColumnConfig<Product>[]>(() => [
    { key: 'code', header: 'Code', sortable: true, sortKey: 'code', width: '8%' },
    {
      key: 'name',
      header: 'Name',
      sortable: true,
      sortKey: 'name',
      width: '18%',
      template: this.nameTemplate(),
    },
    {
      key: 'description',
      header: 'Description',
      width: '20%',
      template: this.descriptionTemplate(),
    },
    {
      key: 'productType',
      header: 'Type',
      sortable: true,
      sortKey: 'product_type',
      width: '6%',
      template: this.typeTemplate(),
    },
    {
      key: 'productCategoryName',
      header: 'Category',
      sortable: true,
      sortKey: 'product_category__name',
      width: '10%',
      template: this.categoryTemplate(),
      filter: {
        options: this.categoryFilterOptions(),
        selectedValues: this.columnFilters()['productCategoryName'] ?? [],
        emptyLabel: 'No categories found',
        searchPlaceholder: 'Search categories...',
      },
    },
    {
      key: 'retailPrice',
      header: 'Retail Price',
      sortable: true,
      sortKey: 'retail_price',
      width: '12%',
      template: this.retailPriceTemplate(),
    },
    {
      key: 'deprecated',
      header: 'Deprecated',
      subtitle: 'Active',
      width: '7%',
      template: this.deprecatedTemplate(),
      filter: {
        options: this.deprecatedFilterOptions,
        selectedValues: this.columnFilters()['deprecated'] ?? [],
        emptyLabel: 'No status found',
        searchPlaceholder: 'Filter status...',
      },
    },
    {
      key: 'createdAt',
      header: 'Added/Updated',
      sortable: true,
      sortKey: 'created_at',
      width: '12%',
      template: this.createdAtTemplate(),
    },
    { key: 'actions', header: 'Actions', width: '4%' },
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
      defaultPageSize: 8,
      defaultOrdering: 'name',
      enableBulkDelete: true,
      enableDelete: true,
    } as BaseListConfig<Product>;
  }

  /**
   * Create the Observable that fetches a page of products.
   * Also fetches category options as a side-effect.
   */
  protected override createListLoader(
    params: ListRequestParams,
  ): Observable<PaginatedResponse<Product>> {
    const deprecatedFilter = this.resolveDeprecatedFilter();
    const categoryParam = this.resolveCategoryFilter();
    const search = params.query?.trim();

    return forkJoin({
      products: this.productsApi.productsList(
        deprecatedFilter.deprecated,
        deprecatedFilter.hideDeprecated,
        params.ordering,
        params.page,
        params.pageSize,
        categoryParam,
        search || undefined,
        undefined,
      ),
      categoryOptions: this.productsApi.productsCategoryOptionsList(
        deprecatedFilter.deprecated,
        deprecatedFilter.hideDeprecated,
        undefined,
      ),
    }).pipe(
      map((response) => {
        this.categoryFilterOptions.set(response.categoryOptions ?? []);
        return response.products;
      }),
    );
  }

  /**
   * Handle column filter change
   */
  onColumnFilterChange(event: ColumnFilterChangeEvent): void {
    if (event.column !== 'deprecated' && event.column !== 'productCategoryName') {
      return;
    }
    this.columnFilters.update((current) => ({
      ...current,
      [event.column]: event.values,
    }));
    this.page.set(1);
    this.reload();
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
      ? this.productsApi.productsForceDeleteCreate(product.id, {
          forceDeleteConfirmed: true,
        } as any)
      : this.productsApi.productsDestroy(product.id);

    deleteRequest.subscribe({
      next: () => {
        this.toast.success(result.forceDelete ? 'Product force deleted' : 'Product deleted');
        this.resetProductDeleteDialog();
        this.reload();
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
        this.reload();
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
        const jobId = extractJobId(response);
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
   * Start public price list print preparation and open the browser print preview.
   */
  async startPrint(): Promise<void> {
    if (this.printInProgress() || this.exportInProgress() || this.importInProgress()) {
      return;
    }

    this.printInProgress.set(true);
    let previewWindow: Window | null = null;

    try {
      previewWindow = openPendingPdfPrintPreviewWindow();
      const response = await firstValueFrom(this.productsApi.productsPriceListPrintStartCreate());
      const jobId = extractJobId(response) ?? '';

      if (!jobId) {
        throw new Error('Print job was started but no job id was returned.');
      }

      const finalJob = await firstValueFrom(
        this.jobService.openProgressDialog(jobId, 'Preparing printable price list...'),
      );

      if (!finalJob) {
        return;
      }

      if (this.isCompletedJob(finalJob)) {
        await this.openPrintedPriceList(jobId, previewWindow);
        this.toast.success('Printable price list opened');
        return;
      }

      if (this.isFailedJob(finalJob)) {
        this.toast.error(finalJob.errorMessage || 'Printable price list generation failed');
      }
    } catch (error) {
      try {
        previewWindow?.close();
      } catch {
        // Ignore popup cleanup failures.
      }
      const message = extractServerErrorMessage(error);
      this.toast.error(
        message
          ? `Failed to open printable price list: ${message}`
          : 'Failed to open printable price list',
      );
    } finally {
      this.printInProgress.set(false);
    }
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
        const jobId = extractJobId(response);
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

  categoryLabel(row?: Product | null): string {
    return this.categoryValue(row) || '—';
  }

  private categoryValue(row?: Product | null): string {
    const value = (row as any)?.productCategoryName;
    return value ? String(value) : '';
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
   * Get retail price value
   */
  retailPriceValue(row: Product): string | number | null {
    return (row as any).retailPrice ?? (row as any).retail_price ?? null;
  }

  private resolveDeprecatedFilter(): { deprecated: boolean | undefined; hideDeprecated: boolean } {
    const selected = new Set(this.columnFilters()['deprecated'] ?? []);
    if (selected.size === 0) {
      return { deprecated: undefined, hideDeprecated: true };
    }
    if (selected.has('active') && selected.has('deprecated')) {
      return { deprecated: undefined, hideDeprecated: false };
    }
    if (selected.has('deprecated')) {
      return { deprecated: true, hideDeprecated: false };
    }
    if (selected.has('active')) {
      return { deprecated: false, hideDeprecated: false };
    }
    return { deprecated: undefined, hideDeprecated: true };
  }

  private resolveCategoryFilter(): string | undefined {
    const selected = this.columnFilters()['productCategoryName'] ?? [];
    if (!selected.length) {
      return undefined;
    }
    return selected.join(',');
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
          this.reload();
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

  private async openPrintedPriceList(jobId: string, previewWindow?: Window | null): Promise<void> {
    const blob = await firstValueFrom(this.productImportExportApi.downloadPriceListPdf(jobId));
    await openPdfPrintPreview(blob, previewWindow);
  }

  private isCompletedJob(job: AsyncJob): boolean {
    return job.status === 'completed';
  }

  private isFailedJob(job: AsyncJob): boolean {
    return job.status === 'failed';
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
    const relatedCounts: any = payload.relatedCounts ?? {};
    const relatedRecords: any = payload.relatedRecords ?? {};
    const relatedRecordsTruncated: any = payload.relatedRecordsTruncated ?? {};

    const taskRecords = this.asArray<any>(relatedRecords.tasks).map((task: any) => ({
      id: this.asNumber(task?.id),
      step: this.asNumber(task?.step),
      name: String(task?.name ?? ''),
    }));

    const applicationRecords = this.asArray<any>(relatedRecords.applications).map(
      (application: any) => ({
        id: this.asNumber(application?.id),
        customerName: String(application?.customerName ?? '—'),
        status: String(application?.status ?? ''),
        statusDisplay: String(application?.statusDisplay ?? ''),
        docDate: application?.docDate ?? null,
        dueDate: application?.dueDate ?? null,
        workflowCount: this.asNumber(application?.workflowCount),
        documentCount: this.asNumber(application?.documentCount),
        invoiceLineCount: this.asNumber(application?.invoiceLineCount),
      }),
    );

    const invoiceLineRecords = this.asArray<any>(relatedRecords.invoiceApplications).map(
      (invoiceLine: any) => ({
        id: this.asNumber(invoiceLine?.id),
        invoiceId: this.asNumber(invoiceLine?.invoiceId),
        invoiceNoDisplay: String(invoiceLine?.invoiceNoDisplay ?? ''),
        invoiceStatus: String(invoiceLine?.invoiceStatus ?? ''),
        customerApplicationId: this.asNullableNumber(invoiceLine?.customerApplicationId),
        customerName: String(invoiceLine?.customerName ?? '—'),
        amount: invoiceLine?.amount ?? '0',
        status: String(invoiceLine?.status ?? ''),
        statusDisplay: String(invoiceLine?.statusDisplay ?? ''),
        paymentCount: this.asNumber(invoiceLine?.paymentCount),
      }),
    );

    return {
      productId: this.asNumber(payload.productId ?? product.id),
      productCode: String(payload.productCode ?? product.code ?? ''),
      productName: String(payload.productName ?? product.name ?? ''),
      canDelete: Boolean(payload.canDelete ?? true),
      requiresForceDelete: Boolean(payload.requiresForceDelete ?? false),
      message: payload.message ?? null,
      relatedCounts: {
        tasks: this.asNumber(relatedCounts.tasks),
        applications: this.asNumber(relatedCounts.applications),
        workflows: this.asNumber(relatedCounts.workflows),
        documents: this.asNumber(relatedCounts.documents),
        invoiceApplications: this.asNumber(relatedCounts.invoiceApplications),
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
        invoiceApplications: Boolean(relatedRecordsTruncated.invoiceApplications),
      },
      recordLimit: this.asNullableNumber(payload.recordLimit) ?? undefined,
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
