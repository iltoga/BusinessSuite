import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  HostListener,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { map } from 'rxjs';

import {
  InvoicesService,
  type DocApplicationInvoice,
  type InvoiceCreateUpdate,
  type InvoiceDetail,
  type Product,
} from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { FormNavigationFacadeService } from '@/features/shared/services/form-navigation-facade.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { CustomerSelectComponent } from '@/shared/components/customer-select/customer-select.component';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardInputDirective } from '@/shared/components/input';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';
import { InvoiceLineItemsSectionComponent } from './invoice-line-items-section.component';

interface BillableProductRow {
  product: Product;
  pendingApplications: DocApplicationInvoice[];
  pendingApplicationsCount: number;
  hasPendingApplications: boolean;
}

interface InvoiceLineInitial {
  id?: number;
  product?: number | null;
  customerApplication?: number | null;
  amount?: number;
  locked?: boolean;
}

@Component({
  selector: 'app-invoice-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
    ZardComboboxComponent,
    ZardDateInputComponent,
    CustomerSelectComponent,
    FormErrorSummaryComponent,
    InvoiceLineItemsSectionComponent,
  ],
  templateUrl: './invoice-form.component.html',
  styleUrls: ['./invoice-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceFormComponent implements OnInit {
  private readonly fb = inject(FormBuilder);
  private readonly route = inject(ActivatedRoute);
  private readonly router = inject(Router);
  private readonly invoicesApi = inject(InvoicesService);
  private readonly toast = inject(GlobalToastService);
  private readonly platformId = inject(PLATFORM_ID);
  private readonly cdr = inject(ChangeDetectorRef);
  private readonly formNavigationFacade = inject(FormNavigationFacadeService);

  private nextLineKey = 1;

  readonly isLoading = signal(false);
  readonly isSaving = signal(false);
  readonly isEditMode = signal(false);
  readonly invoice = signal<InvoiceDetail | null>(null);
  readonly billableProducts = signal<BillableProductRow[]>([]);
  readonly sourceApplicationId = signal<number | null>(null);
  readonly lockCustomerFromSource = signal(false);

  readonly form = this.fb.group({
    customer: [null as number | null, Validators.required],
    invoiceNo: [null as number | null],
    invoiceDate: [new Date(), Validators.required],
    dueDate: [new Date(), Validators.required],
    notes: [''],
    sent: [false],
    invoiceApplications: this.fb.array<FormGroup>([]),
  });

  readonly formErrorLabels: Record<string, string> = {
    customer: 'Customer',
    invoiceNo: 'Invoice No',
    invoiceDate: 'Invoice Date',
    dueDate: 'Due Date (Payment)',
    notes: 'Notes',
    sent: 'Sent',
    invoiceApplications: 'Invoice Products',
    invoiceApplicationsProduct: 'Product',
    invoiceApplicationsCustomerApplication: 'Linked Application',
    invoiceApplicationsAmount: 'Amount',
  };

  readonly totalAmount = computed(() =>
    this.invoiceApplications.controls.reduce((sum, group) => {
      const amount = Number(group.get('amount')?.value ?? 0);
      return sum + (Number.isNaN(amount) ? 0 : amount);
    }, 0),
  );
  readonly billableProductOptions = computed<ZardComboboxOption[]>(() =>
    this.billableProducts().map((row) => ({
      value: String(row.product.id),
      label: this.getBillableProductLabel(row),
    })),
  );

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    if (event.key === 'Escape') {
      event.preventDefault();
      this.goBack();
      return;
    }

    const isSaveKey = (event.ctrlKey || event.metaKey) && (event.key === 's' || event.key === 'S');
    if (isSaveKey) {
      event.preventDefault();
      this.onSubmit();
      return;
    }

    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.goBack();
    }
  }

  get invoiceApplications(): FormArray<FormGroup> {
    return this.form.get('invoiceApplications') as FormArray<FormGroup>;
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

    const idParam = this.route.snapshot.paramMap.get('id');
    const applicationId = this.route.snapshot.queryParamMap.get('applicationId');

    if (idParam) {
      this.isEditMode.set(true);
      this.loadInvoice(Number(idParam));
      return;
    }

    if (applicationId) {
      this.loadFromApplication(Number(applicationId));
    } else {
      this.addLineItem({}, { manual: false, skipAutoExpand: true });
    }

    this.proposeInvoiceNo(this.form.get('invoiceDate')?.value);
    this.form.get('invoiceDate')?.valueChanges.subscribe((value) => {
      if (this.isEditMode()) return;
      const invoiceNoCtrl = this.form.get('invoiceNo');
      if (invoiceNoCtrl && !invoiceNoCtrl.dirty) {
        this.proposeInvoiceNo(value);
      }
    });

    this.form.get('customer')?.valueChanges.subscribe((value) => {
      if (this.isEditMode() || this.lockCustomerFromSource()) {
        return;
      }
      if (!value) {
        this.billableProducts.set([]);
        this.invoiceApplications.clear();
        this.addLineItem({}, { manual: false, skipAutoExpand: true });
        return;
      }

      this.invoiceApplications.clear();
      this.addLineItem({}, { manual: false, skipAutoExpand: true });
      this.loadBillableProducts(value);
    });
  }

  goBack(): void {
    this.formNavigationFacade.goBackFromInvoiceForm({
      router: this.router,
      state: history.state as any,
      invoiceId: this.invoice()?.id ?? null,
    });
  }

  addLineItem(
    initial: InvoiceLineInitial = {},
    options: { manual?: boolean; skipAutoExpand?: boolean } = {},
  ): void {
    const manual = options.manual ?? true;
    if (manual && !this.form.get('customer')?.value) {
      this.toast.error('Please select a customer first.');
      return;
    }

    const lineKey = this.nextLineKey++;
    const group = this.fb.group({
      id: [initial.id ?? null],
      lineKey: [lineKey],
      locked: [!!initial.locked],
      product: [initial.product ?? null, Validators.required],
      customerApplication: [initial.customerApplication ?? null],
      amount: [initial.amount ?? 0, [Validators.required, Validators.min(0)]],
    });

    group.get('product')?.valueChanges.subscribe((value) => {
      this.onLineProductChanged(group, value, !(options.skipAutoExpand ?? false));
    });

    group.get('customerApplication')?.valueChanges.subscribe((value) => {
      this.onLineApplicationChanged(group, value);
    });

    this.invoiceApplications.push(group);

    if (initial.locked) {
      group.get('product')?.disable({ emitEvent: false });
      group.get('customerApplication')?.disable({ emitEvent: false });
    }

    if (initial.product && initial.customerApplication) {
      const app = this.findPendingApplicationById(initial.customerApplication);
      if (app) {
        group.get('amount')?.setValue(this.resolveApplicationPrice(app), { emitEvent: false });
      }
    } else if (initial.product && initial.amount === undefined) {
      group
        .get('amount')
        ?.setValue(this.resolveProductPrice(initial.product), { emitEvent: false });
    }
  }

  removeLineItem(index: number): void {
    const group = this.invoiceApplications.at(index);
    if (!group || this.isLineLocked(group) || this.invoiceApplications.length <= 1) {
      return;
    }
    this.invoiceApplications.removeAt(index);
  }

  isLineLocked(group: FormGroup): boolean {
    return !!group.get('locked')?.value;
  }

  selectedProductPendingCount(group: FormGroup): number {
    const productId = Number(group.get('product')?.value ?? 0);
    if (!productId) {
      return 0;
    }
    const row = this.findBillableProduct(productId);
    return row?.pendingApplicationsCount ?? 0;
  }

  availablePendingApplicationsForLine(group: FormGroup): DocApplicationInvoice[] {
    const productId = Number(group.get('product')?.value ?? 0);
    if (!productId) {
      return [];
    }

    const lineKey = Number(group.get('lineKey')?.value ?? 0);
    const selectedIds = this.selectedCustomerApplicationIds(lineKey);
    const selectedCurrentId = Number(group.get('customerApplication')?.value ?? 0) || null;

    const row = this.findBillableProduct(productId);
    if (!row) {
      return [];
    }

    return row.pendingApplications.filter(
      (app) =>
        !selectedIds.has(app.id) || (selectedCurrentId !== null && app.id === selectedCurrentId),
    );
  }

  save(): void {
    if (this.form.invalid) {
      this.toast.error('Please fix validation errors before saving.');
      return;
    }

    this.isSaving.set(true);
    const raw = this.form.getRawValue();

    const payload = {
      customer: raw.customer!,
      invoiceNo: raw.invoiceNo ?? undefined,
      invoiceDate: this.toIsoDate(raw.invoiceDate),
      dueDate: this.toIsoDate(raw.dueDate),
      notes: raw.notes ?? '',
      sent: raw.sent ?? false,
      invoiceApplications: (raw.invoiceApplications ?? []).map((item: any) => ({
        id: item.id ?? undefined,
        product: Number(item.product),
        customerApplication: item.customerApplication ? Number(item.customerApplication) : null,
        amount: String(item.amount ?? 0),
      })),
    } as InvoiceCreateUpdate;

    const fromState = history.state?.from;
    const returnUrl = history.state?.returnUrl;
    const customerId = history.state?.customerId;
    const searchQuery = history.state?.searchQuery;
    const page = Number(history.state?.page);
    const detailState: Record<string, unknown> = {
      from: fromState,
      returnUrl,
      customerId,
      searchQuery,
      page: Number.isFinite(page) && page > 0 ? Math.floor(page) : undefined,
    };

    if (this.isEditMode() && this.invoice()) {
      this.invoicesApi.invoicesUpdate(this.invoice()!.id, payload).subscribe({
        next: (invoice: InvoiceCreateUpdate) => {
          this.toast.success('Invoice updated');
          this.router.navigate(['/invoices', invoice.id], { state: detailState });
        },
        error: (error) => {
          applyServerErrorsToForm(this.form, error);
          this.form.markAllAsTouched();
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to update invoice: ${message}` : 'Failed to update invoice',
          );
          this.isSaving.set(false);
        },
      });
      return;
    }

    this.invoicesApi.invoicesCreate(payload).subscribe({
      next: (invoice: InvoiceCreateUpdate) => {
        this.toast.success('Invoice created');
        this.router.navigate(['/invoices', invoice.id], { state: detailState });
      },
      error: (error) => {
        applyServerErrorsToForm(this.form, error);
        this.form.markAllAsTouched();
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to create invoice: ${message}` : 'Failed to create invoice',
        );
        this.isSaving.set(false);
      },
    });
  }

  onSubmit(): void {
    this.save();
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—';
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      maximumFractionDigits: 0,
    }).format(value);
  }

  getBillableProductLabel(row: BillableProductRow): string {
    return `${row.product.code} - ${row.product.name}`;
  }

  toComboboxValue(value: unknown): string | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    return String(value);
  }

  availablePendingApplicationOptionsForLine(group: FormGroup): ZardComboboxOption[] {
    return this.availablePendingApplicationsForLine(group).map((app) => ({
      value: String(app.id),
      label: `#${app.id} \u00b7 ${app.customer?.fullName ?? 'Unknown customer'}`,
    }));
  }

  onLineProductComboboxChange(group: FormGroup, value: string | null): void {
    group.get('product')?.setValue(this.parseComboboxNumericValue(value));
  }

  onLineCustomerApplicationComboboxChange(group: FormGroup, value: string | null): void {
    group.get('customerApplication')?.setValue(this.parseComboboxNumericValue(value));
  }

  private selectedCustomerApplicationIds(excludeLineKey?: number): Set<number> {
    const selected = new Set<number>();
    for (const line of this.invoiceApplications.getRawValue() as any[]) {
      const lineKey = Number(line.lineKey ?? 0);
      if (excludeLineKey && lineKey === excludeLineKey) {
        continue;
      }
      const appId = Number(line.customerApplication ?? 0);
      if (appId) {
        selected.add(appId);
      }
    }
    return selected;
  }

  private onLineProductChanged(
    group: FormGroup,
    rawProductId: unknown,
    allowAutoExpand: boolean,
  ): void {
    const productId = Number(rawProductId ?? 0);
    if (!productId) {
      group.get('customerApplication')?.setValue(null, { emitEvent: false });
      group.get('amount')?.setValue(0, { emitEvent: false });
      return;
    }

    const currentAppId = Number(group.get('customerApplication')?.value ?? 0) || null;

    if (allowAutoExpand && !currentAppId) {
      const availablePending = this.availablePendingApplicationsForLine(group);
      if (availablePending.length > 0) {
        const [first, ...rest] = availablePending;
        group.get('customerApplication')?.setValue(first.id, { emitEvent: false });
        group.get('amount')?.setValue(this.resolveApplicationPrice(first), { emitEvent: false });

        for (const pendingApp of rest) {
          this.addLineItem(
            {
              product: productId,
              customerApplication: pendingApp.id,
              amount: this.resolveApplicationPrice(pendingApp),
            },
            { manual: false, skipAutoExpand: true },
          );
        }
        this.cdr.markForCheck();
        return;
      }
    }

    if (currentAppId) {
      const selectedApp = this.findPendingApplicationById(currentAppId);
      if (!selectedApp || selectedApp.product?.id !== productId) {
        group.get('customerApplication')?.setValue(null, { emitEvent: false });
        group.get('amount')?.setValue(this.resolveProductPrice(productId), { emitEvent: false });
        return;
      }

      group
        .get('amount')
        ?.setValue(this.resolveApplicationPrice(selectedApp), { emitEvent: false });
      return;
    }

    group.get('amount')?.setValue(this.resolveProductPrice(productId), { emitEvent: false });
  }

  private onLineApplicationChanged(group: FormGroup, rawApplicationId: unknown): void {
    const applicationId = Number(rawApplicationId ?? 0);
    if (!applicationId) {
      const productId = Number(group.get('product')?.value ?? 0);
      group.get('amount')?.setValue(this.resolveProductPrice(productId), { emitEvent: false });
      return;
    }

    const application = this.findPendingApplicationById(applicationId);
    if (!application) {
      return;
    }

    const applicationProductId = application.product?.id;
    if (applicationProductId && group.get('product')?.value !== applicationProductId) {
      group.get('product')?.setValue(applicationProductId, { emitEvent: false });
    }
    group.get('amount')?.setValue(this.resolveApplicationPrice(application), { emitEvent: false });
  }

  private findBillableProduct(productId: number): BillableProductRow | undefined {
    return this.billableProducts().find((row) => row.product.id === productId);
  }

  private findPendingApplicationById(applicationId: number): DocApplicationInvoice | undefined {
    for (const row of this.billableProducts()) {
      const app = row.pendingApplications.find((candidate) => candidate.id === applicationId);
      if (app) {
        return app;
      }
    }
    return undefined;
  }

  private resolveProductPrice(productId: number | null | undefined): number {
    if (!productId) {
      return 0;
    }
    const row = this.findBillableProduct(productId);
    return this.resolveProductPriceFromProduct(row?.product);
  }

  private resolveProductPriceFromProduct(product: Product | null | undefined): number {
    if (!product) {
      return 0;
    }
    const retail = (product as any).retailPrice;
    const base = (product as any).basePrice;
    const price = Number(retail ?? base ?? 0);
    return Number.isNaN(price) ? 0 : price;
  }

  private resolveApplicationPrice(app: DocApplicationInvoice): number {
    return this.resolveProductPriceFromProduct(app.product as Product);
  }

  private loadFromApplication(applicationId: number): void {
    this.isLoading.set(true);

    this.invoicesApi.invoicesFromApplicationPrefillRetrieve(applicationId).subscribe({
      next: (response) => {
        const payload = (response ?? null) as Record<string, any> | null;
        const customerId = payload?.['customer']?.id ?? null;
        const sourceLine = payload?.['invoiceApplication'] ?? null;
        const sourceApplication = payload?.['sourceApplication'] ?? null;
        const sourceApplicationId = sourceLine?.['customerApplication'] ?? null;
        const sourceProductId = sourceLine?.['product'] ?? null;

        if (!customerId || !sourceProductId || !sourceApplicationId) {
          this.toast.error('Invalid source application prefill payload.');
          this.addLineItem({}, { manual: false, skipAutoExpand: true });
          this.isLoading.set(false);
          return;
        }

        this.sourceApplicationId.set(Number(sourceApplicationId));
        this.lockCustomerFromSource.set(true);
        this.form.get('customer')?.setValue(customerId, { emitEvent: false });
        this.form.get('customer')?.disable({ emitEvent: false });

        this.fetchBillableProducts(customerId).subscribe({
          next: (rows) => {
            this.billableProducts.set(
              this.ensureSourceApplicationIncluded(rows, sourceApplication),
            );
            this.invoiceApplications.clear();
            this.addLineItem(
              {
                product: Number(sourceProductId),
                customerApplication: Number(sourceApplicationId),
                amount: Number(sourceLine['amount'] ?? 0),
                locked: true,
              },
              { manual: false, skipAutoExpand: true },
            );
            this.isLoading.set(false);
            this.cdr.markForCheck();
          },
          error: (error) => {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message
                ? `Failed to load billable products: ${message}`
                : 'Failed to load billable products',
            );
            this.invoiceApplications.clear();
            this.addLineItem({}, { manual: false, skipAutoExpand: true });
            this.isLoading.set(false);
          },
        });
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message
            ? `Failed to load source application: ${message}`
            : 'Failed to load source application',
        );
        this.invoiceApplications.clear();
        this.addLineItem({}, { manual: false, skipAutoExpand: true });
        this.isLoading.set(false);
      },
    });
  }

  private loadInvoice(id: number): void {
    this.isLoading.set(true);
    this.invoicesApi.invoicesRetrieve(id).subscribe({
      next: (invoice: InvoiceDetail) => {
        this.invoice.set(invoice);
        this.form.patchValue({
          customer: invoice.customer?.id ?? null,
          invoiceNo: invoice.invoiceNo ?? null,
          invoiceDate: invoice.invoiceDate ? new Date(invoice.invoiceDate) : new Date(),
          dueDate: invoice.dueDate ? new Date(invoice.dueDate) : new Date(),
          notes: invoice.notes ?? '',
          sent: invoice.sent ?? false,
        });

        this.form.get('customer')?.disable({ emitEvent: false });
        this.form.get('invoiceNo')?.disable({ emitEvent: false });

        const customerId = invoice.customer?.id;
        if (!customerId) {
          this.invoiceApplications.clear();
          this.addLineItem({}, { manual: false, skipAutoExpand: true });
          this.isLoading.set(false);
          return;
        }

        this.fetchBillableProducts(customerId, invoice.id).subscribe({
          next: (rows) => {
            this.billableProducts.set(rows);
            this.invoiceApplications.clear();

            for (const item of invoice.invoiceApplications ?? []) {
              const productId = item.product?.id ?? item.customerApplication?.product?.id ?? null;
              this.addLineItem(
                {
                  id: item.id,
                  product: productId,
                  customerApplication: item.customerApplication?.id ?? null,
                  amount: Number(item.amount ?? 0),
                },
                { manual: false, skipAutoExpand: true },
              );
            }

            if ((invoice.invoiceApplications ?? []).length === 0) {
              this.addLineItem({}, { manual: false, skipAutoExpand: true });
            }

            this.isLoading.set(false);
            this.cdr.markForCheck();
          },
          error: (error) => {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message
                ? `Failed to load billable products: ${message}`
                : 'Failed to load billable products',
            );
            this.invoiceApplications.clear();
            this.addLineItem({}, { manual: false, skipAutoExpand: true });
            this.isLoading.set(false);
          },
        });
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(message ? `Failed to load invoice: ${message}` : 'Failed to load invoice');
        this.isLoading.set(false);
      },
    });
  }

  private loadBillableProducts(customerId: number, currentInvoiceId?: number): void {
    this.fetchBillableProducts(customerId, currentInvoiceId).subscribe({
      next: (rows) => {
        this.billableProducts.set(rows);
        this.cdr.markForCheck();
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message
            ? `Failed to load billable products: ${message}`
            : 'Failed to load billable products',
        );
      },
    });
  }

  private fetchBillableProducts(customerId: number, currentInvoiceId?: number) {
    return this.invoicesApi
      .invoicesGetBillableProductsRetrieve(customerId, currentInvoiceId)
      .pipe(map((rows) => this.normalizeBillableRows(rows)));
  }

  private normalizeBillableRows(rows: unknown): BillableProductRow[] {
    const list = Array.isArray(rows)
      ? rows
      : Array.isArray((rows as any)?.results)
        ? (rows as any).results
        : [];
    return list
      .map((row: any) => {
        const product = (row?.product ?? null) as Product | null;
        if (!product || typeof product.id !== 'number') {
          return null;
        }

        const pendingApplications = (row?.pendingApplications ??
          row?.pending_applications ??
          []) as DocApplicationInvoice[];
        const pendingApplicationsCount = Number(
          row?.pendingApplicationsCount ??
            row?.pending_applications_count ??
            pendingApplications.length,
        );
        const hasPendingApplications =
          row?.hasPendingApplications ??
          row?.has_pending_applications ??
          pendingApplicationsCount > 0;

        return {
          product,
          pendingApplications: Array.isArray(pendingApplications) ? pendingApplications : [],
          pendingApplicationsCount: Number.isFinite(pendingApplicationsCount)
            ? pendingApplicationsCount
            : 0,
          hasPendingApplications: Boolean(hasPendingApplications),
        } as BillableProductRow;
      })
      .filter((row: BillableProductRow | null): row is BillableProductRow => row !== null);
  }

  private ensureSourceApplicationIncluded(
    rows: BillableProductRow[],
    rawSourceApplication: unknown,
  ): BillableProductRow[] {
    const sourceApplication = this.toDocApplicationInvoice(rawSourceApplication);
    const sourceApplicationId = Number(sourceApplication?.id ?? 0);
    const sourceProduct = sourceApplication?.product as Product | null | undefined;
    const sourceProductId = Number(sourceProduct?.id ?? 0);

    if (!sourceApplication || !sourceApplicationId || !sourceProductId || !sourceProduct) {
      return rows;
    }

    const existingRowIndex = rows.findIndex((row) => row.product.id === sourceProductId);
    if (existingRowIndex === -1) {
      return this.sortBillableRows([
        ...rows,
        {
          product: sourceProduct,
          pendingApplications: [sourceApplication],
          pendingApplicationsCount: 1,
          hasPendingApplications: true,
        },
      ]);
    }

    const existingRow = rows[existingRowIndex];
    if (
      existingRow.pendingApplications.some((application) => application.id === sourceApplicationId)
    ) {
      return rows;
    }

    const updatedRow: BillableProductRow = {
      ...existingRow,
      pendingApplications: [sourceApplication, ...existingRow.pendingApplications],
      pendingApplicationsCount: existingRow.pendingApplicationsCount + 1,
      hasPendingApplications: true,
    };

    return rows.map((row, index) => (index === existingRowIndex ? updatedRow : row));
  }

  private toDocApplicationInvoice(value: unknown): DocApplicationInvoice | null {
    if (!value || typeof value !== 'object') {
      return null;
    }

    const candidate = value as Partial<DocApplicationInvoice> & {
      product?: Partial<Product> | null;
    };
    if (typeof candidate.id !== 'number') {
      return null;
    }
    if (!candidate.product || typeof candidate.product.id !== 'number') {
      return null;
    }

    return candidate as DocApplicationInvoice;
  }

  private sortBillableRows(rows: BillableProductRow[]): BillableProductRow[] {
    return [...rows].sort((left, right) => {
      if (left.hasPendingApplications !== right.hasPendingApplications) {
        return left.hasPendingApplications ? -1 : 1;
      }
      return (left.product.name ?? '').localeCompare(right.product.name ?? '', undefined, {
        sensitivity: 'base',
      });
    });
  }

  private toIsoDate(value: Date | string | null): string | null {
    if (!value) return null;
    if (typeof value === 'string') {
      const iso = value.match(/^(\d{4})-(\d{2})-(\d{2})$/);
      if (iso) {
        return `${iso[1]}-${iso[2]}-${iso[3]}`;
      }
    }
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private parseComboboxNumericValue(value: string | null): number | null {
    if (!value) {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private proposeInvoiceNo(invoiceDate?: Date | string | null): void {
    if (!invoiceDate) return;
    const date = invoiceDate instanceof Date ? invoiceDate : new Date(invoiceDate);
    if (Number.isNaN(date.getTime())) return;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const dateStr = `${year}-${month}-${day}`;

    this.invoicesApi.invoicesProposeRetrieve(dateStr).subscribe({
      next: (res) => {
        const ctrl = this.form.get('invoiceNo');
        if (ctrl && !ctrl.dirty) {
          const proposedNo = res.invoiceNo;
          if (proposedNo) {
            ctrl.setValue(proposedNo, { emitEvent: false });
            ctrl.markAsPristine();
            this.cdr.markForCheck();
          }
        }
      },
      error: () => {
        // Non-blocking helper.
      },
    });
  }
}
