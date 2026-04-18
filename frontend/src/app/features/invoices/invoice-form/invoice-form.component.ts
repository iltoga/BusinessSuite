import { isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  DestroyRef,
  HostListener,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { map } from 'rxjs';

import {
  InvoicesService,
  type DocApplicationInvoice,
  type InvoiceCreateUpdate,
  type InvoiceCreateUpdateRequest,
  type InvoiceDetail,
  type Product,
} from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { unwrapApiRecord } from '@/core/utils/api-envelope';
import { FormNavigationFacadeService } from '@/features/shared/services/form-navigation-facade.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import type { ZardComboboxOption } from '@/shared/components/combobox';
import { CustomerSelectComponent } from '@/shared/components/customer-select/customer-select.component';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardInputDirective } from '@/shared/components/input';
import { toApiDate } from '@/shared/utils/date-parsing';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';
import {
  normalizeBillableRows,
  parseComboboxNumericValue,
  resolveProductPriceFromProduct,
  type BillableProductRow,
  type InvoiceLineInitial,
} from './invoice-form-normalizers';
import { InvoiceLineItemsSectionComponent } from './invoice-line-items-section.component';

@Component({
  selector: 'app-invoice-form',
  standalone: true,
  imports: [
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
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
  private readonly destroyRef = inject(DestroyRef);

  private nextLineKey = 1;

  readonly isLoading = signal(false);
  readonly isSaving = signal(false);
  readonly isEditMode = signal(false);
  readonly invoice = signal<InvoiceDetail | null>(null);
  readonly billableProducts = signal<BillableProductRow[]>([]);
  readonly lockCustomerFromSource = signal(false);
  readonly totalAmount = signal(0);

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
    invoiceApplications: 'Invoice Lines',
    invoiceApplicationsProduct: 'Product',
    invoiceApplicationsCustomerApplication: 'Linked Application',
    invoiceApplicationsQuantity: 'Qty',
    invoiceApplicationsNotes: 'Line Notes',
    invoiceApplicationsAmount: 'Amount',
  };

  readonly billableProductOptions = computed<ZardComboboxOption[]>(() =>
    this.billableProducts().map((row) => ({
      value: String(row.product.id),
      label: this.getBillableProductLabel(row),
    })),
  );

  readonly availableApplications = computed<DocApplicationInvoice[]>(() => {
    const applications: DocApplicationInvoice[] = [];
    const seen = new Set<number>();
    for (const row of this.billableProducts()) {
      for (const application of row.pendingApplications) {
        if (seen.has(application.id)) {
          continue;
        }
        seen.add(application.id);
        applications.push(application);
      }
    }
    return applications;
  });

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
      this.addLineItem({}, { manual: false });
    }

    this.proposeInvoiceNo(this.form.get('invoiceDate')?.value);
    this.form
      .get('invoiceDate')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        if (this.isEditMode()) return;
        const invoiceNoCtrl = this.form.get('invoiceNo');
        if (invoiceNoCtrl && !invoiceNoCtrl.dirty) {
          this.proposeInvoiceNo(value);
        }
      });

    this.form
      .get('customer')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        if (this.isEditMode() || this.lockCustomerFromSource()) {
          return;
        }
        if (!value) {
          this.billableProducts.set([]);
          this.invoiceApplications.clear();
          this.addLineItem({}, { manual: false });
          return;
        }

        this.invoiceApplications.clear();
        this.addLineItem({}, { manual: false });
        this.loadBillableProducts(value);
      });

    this.invoiceApplications.valueChanges
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => this.updateTotalAmount());

    this.updateTotalAmount();
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
    options: { manual?: boolean } = {},
  ): void {
    const manual = options.manual ?? true;
    if (manual && !this.form.get('customer')?.value) {
      this.toast.error('Please select a customer first.');
      return;
    }

    const lineKey = this.nextLineKey++;
    const identityLocked = !!initial.identityLocked || !!initial.locked;
    const group = this.fb.group({
      id: [initial.id ?? null],
      lineKey: [lineKey],
      identityLocked: [identityLocked],
      product: [initial.product ?? null, Validators.required],
      customerApplication: [initial.customerApplication ?? null],
      quantity: [initial.quantity ?? 1, [Validators.required, Validators.min(1)]],
      notes: [initial.notes ?? ''],
      amount: [initial.amount ?? 0, [Validators.required, Validators.min(0)]],
      amountOverridden: [!!initial.amountOverridden],
    });

    group
      .get('product')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.onLineProductChanged(group, value);
      });

    group
      .get('customerApplication')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.onLineApplicationChanged(group, value);
      });

    group
      .get('quantity')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe((value) => {
        this.onLineQuantityChanged(group, value);
      });

    group
      .get('amount')
      ?.valueChanges.pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe(() => {
        group.get('amountOverridden')?.setValue(true, { emitEvent: false });
        this.updateTotalAmount();
      });

    this.invoiceApplications.push(group);

    if (identityLocked) {
      group.get('product')?.disable({ emitEvent: false });
      group.get('customerApplication')?.disable({ emitEvent: false });
    }

    const quantity = this.getLineQuantity(group);
    if (initial.product && initial.customerApplication && initial.amount === undefined) {
      const app = this.findPendingApplicationById(initial.customerApplication);
      if (app) {
        group
          .get('amount')
          ?.setValue(this.resolveApplicationPrice(app) * quantity, { emitEvent: false });
      }
    } else if (initial.product && initial.amount === undefined) {
      group
        .get('amount')
        ?.setValue(this.resolveProductPrice(initial.product) * quantity, { emitEvent: false });
    }

    this.updateTotalAmount();
  }

  removeLineItem(index: number): void {
    const group = this.invoiceApplications.at(index);
    if (!group || this.invoiceApplications.length <= 1) {
      return;
    }
    this.invoiceApplications.removeAt(index);
    this.updateTotalAmount();
  }

  moveLineItem(index: number, direction: -1 | 1): void {
    const targetIndex = index + direction;
    if (
      index < 0 ||
      targetIndex < 0 ||
      index >= this.invoiceApplications.length ||
      targetIndex >= this.invoiceApplications.length
    ) {
      return;
    }

    const group = this.invoiceApplications.at(index);
    if (!group) {
      return;
    }

    this.invoiceApplications.removeAt(index);
    this.invoiceApplications.insert(targetIndex, group);
    this.invoiceApplications.markAsDirty();
    this.updateTotalAmount();
  }

  isLineLocked(group: FormGroup): boolean {
    return !!group.get('identityLocked')?.value;
  }

  selectedProductPendingCount(group: FormGroup): number {
    const productId = this.resolveLineProductId(group);
    if (!productId) {
      return 0;
    }
    const row = this.findBillableProduct(productId);
    return row?.pendingApplicationsCount ?? 0;
  }

  availablePendingApplicationsForLine(group: FormGroup): DocApplicationInvoice[] {
    const lineKey = Number(group.get('lineKey')?.value ?? 0);
    const selectedIds = this.selectedCustomerApplicationIds(lineKey);
    const selectedCurrentId = Number(group.get('customerApplication')?.value ?? 0) || null;
    const productId = this.resolveLineProductId(group);
    const applications = productId
      ? this.availableApplications().filter((application) => Number(application.product?.id ?? 0) === productId)
      : [...this.availableApplications()];

    return applications.filter(
      (application) =>
        !selectedIds.has(application.id) ||
        (selectedCurrentId !== null && application.id === selectedCurrentId),
    );
  }

  save(): void {
    if (this.invoiceApplications.length === 0) {
      this.toast.error('An invoice must have at least one line item.');
      return;
    }

    const duplicateApplicationId = this.findDuplicateCustomerApplicationId();
    if (duplicateApplicationId) {
      this.toast.error(
        `Linked application #${duplicateApplicationId} is selected more than once in this invoice.`,
      );
      return;
    }

    if (this.form.invalid) {
      this.toast.error('Please fix validation errors before saving.');
      return;
    }

    this.isSaving.set(true);
    const raw = this.form.getRawValue();
    const invoiceDate = toApiDate(raw.invoiceDate);
    const dueDate = toApiDate(raw.dueDate);
    if (!invoiceDate || !dueDate) {
      this.toast.error('Invoice and due dates are required.');
      this.isSaving.set(false);
      return;
    }

    const payload: InvoiceCreateUpdateRequest = {
      customer: raw.customer!,
      invoiceNo: raw.invoiceNo ?? undefined,
      invoiceDate,
      dueDate,
      notes: raw.notes ?? '',
      sent: raw.sent ?? false,
      invoiceApplications: (raw.invoiceApplications ?? []).map((item: any, index: number) => ({
        id: item.id ?? undefined,
        sortOrder: index,
        product: Number(item.product),
        customerApplication: item.customerApplication ? Number(item.customerApplication) : null,
        quantity: this.normalizeLineQuantity(item.quantity),
        notes: this.normalizeLineNotes(item.notes),
        amount: String(item.amount ?? 0),
      })),
    };

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
      this.invoicesApi
        .invoicesUpdate({ id: this.invoice()!.id, invoiceCreateUpdateRequest: payload })
        .subscribe({
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

    this.invoicesApi.invoicesCreate({ invoiceCreateUpdateRequest: payload }).subscribe({
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
    const options = this.availablePendingApplicationsForLine(group).map((app) =>
      this.toInvoiceApplicationOption(app),
    );
    const currentApplication = this.resolveLineApplication(group);
    if (!currentApplication) {
      return options;
    }

    const currentOption = this.toInvoiceApplicationOption(currentApplication);
    return options.some((option) => option.value === currentOption.value)
      ? options
      : [currentOption, ...options];
  }

  onLineProductComboboxChange(group: FormGroup, value: string | null): void {
    group.get('product')?.setValue(parseComboboxNumericValue(value));
  }

  onLineCustomerApplicationComboboxChange(group: FormGroup, value: string | null): void {
    group.get('customerApplication')?.setValue(parseComboboxNumericValue(value));
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

  private findDuplicateCustomerApplicationId(): number | null {
    const seen = new Set<number>();
    const lines =
      typeof (this.invoiceApplications as any)?.getRawValue === 'function'
        ? ((this.invoiceApplications as any).getRawValue() as any[])
        : (((this.invoiceApplications as any)?.value ?? []) as any[]);
    for (const line of lines) {
      const appId = Number(line.customerApplication ?? 0);
      if (!appId) {
        continue;
      }
      if (seen.has(appId)) {
        return appId;
      }
      seen.add(appId);
    }
    return null;
  }

  availableProductOptionsForLine(group: FormGroup): ZardComboboxOption[] {
    const productId = this.resolveLineProductId(group);
    if (this.isLineLocked(group) || Number(group.get('customerApplication')?.value ?? 0)) {
      const option = this.resolveProductOption(productId, group);
      return option ? [option] : this.billableProductOptions();
    }

    return this.billableProductOptions();
  }

  private onLineProductChanged(group: FormGroup, rawProductId: unknown): void {
    const productId = Number(rawProductId ?? 0);
    if (!productId) {
      group.get('customerApplication')?.setValue(null, { emitEvent: false });
      group.get('amount')?.setValue(0, { emitEvent: false });
      this.updateTotalAmount();
      return;
    }

    const currentAppId = Number(group.get('customerApplication')?.value ?? 0) || null;

    if (currentAppId) {
      const selectedApp = this.findPendingApplicationById(currentAppId);
      if (!selectedApp || selectedApp.product?.id !== productId) {
        group.get('customerApplication')?.setValue(null, { emitEvent: false });
        this.updateLineAmountFromDefault(group);
        return;
      }

      this.updateLineAmountFromDefault(group);
      return;
    }

    this.updateLineAmountFromDefault(group);
  }

  private onLineApplicationChanged(group: FormGroup, rawApplicationId: unknown): void {
    const applicationId = Number(rawApplicationId ?? 0);
    if (!applicationId) {
      this.updateLineAmountFromDefault(group);
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
    this.updateLineAmountFromDefault(group);
  }

  private onLineQuantityChanged(group: FormGroup, _rawQuantity: unknown): void {
    this.updateLineAmountFromDefault(group);
  }

  private findBillableProduct(productId: number): BillableProductRow | undefined {
    return this.billableProducts().find((row) => row.product.id === productId);
  }

  private findAvailableApplicationById(applicationId: number): DocApplicationInvoice | undefined {
    if (!applicationId) {
      return undefined;
    }

    const available = this.availableApplications().find((application) => application.id === applicationId);
    if (available) {
      return available;
    }

    return this.findCurrentInvoiceApplicationForLine(applicationId) ?? undefined;
  }

  private resolveLineApplication(group: FormGroup): DocApplicationInvoice | null {
    const applicationId = Number(group.get('customerApplication')?.value ?? 0);
    if (!applicationId) {
      return null;
    }

    return this.findAvailableApplicationById(applicationId) ?? null;
  }

  private resolveLineProductId(group: FormGroup): number | null {
    const application = this.resolveLineApplication(group);
    const applicationProductId = Number(application?.product?.id ?? 0);
    if (applicationProductId) {
      return applicationProductId;
    }

    const productId = Number(group.get('product')?.value ?? 0);
    return productId || null;
  }

  private resolveProductOption(productId: number | null, group: FormGroup): ZardComboboxOption | null {
    if (!productId) {
      return null;
    }

    const row = this.findBillableProduct(productId);
    if (row) {
      return {
        value: String(row.product.id),
        label: this.getBillableProductLabel(row),
      };
    }

    const application = this.resolveLineApplication(group);
    const product = application?.product;
    if (product && product.id === productId) {
      return {
        value: String(product.id),
        label: `${product.code} - ${product.name}`,
      };
    }

    const invoiceProduct = this.findCurrentInvoiceProductOption(productId);
    if (invoiceProduct) {
      return invoiceProduct;
    }

    return this.billableProductOptions().find((option) => Number(option.value) === productId) ?? null;
  }

  private findCurrentInvoiceApplicationForLine(applicationId: number): DocApplicationInvoice | null;
  private findCurrentInvoiceApplicationForLine(group: FormGroup): DocApplicationInvoice | null;
  private findCurrentInvoiceApplicationForLine(arg: number | FormGroup): DocApplicationInvoice | null {
    const applicationId = typeof arg === 'number' ? arg : Number(arg.get('customerApplication')?.value ?? 0);
    if (!applicationId) {
      return null;
    }

    const productId = typeof arg === 'number' ? null : Number(arg.get('product')?.value ?? 0);
    const invoiceApplications = this.invoice()?.invoiceApplications ?? [];
    const invoiceApplication = invoiceApplications.find((item) => {
      if (item.customerApplication?.id !== applicationId) {
        return false;
      }

      return !productId || Number(item.product?.id ?? 0) === productId;
    });

    return invoiceApplication?.customerApplication ?? null;
  }

  private findCurrentInvoiceProductOption(productId: number): ZardComboboxOption | null {
    if (!productId) {
      return null;
    }

    const invoiceApplications = this.invoice()?.invoiceApplications ?? [];
    const invoiceApplication = invoiceApplications.find((item) => Number(item.product?.id ?? 0) === productId);
    const product = invoiceApplication?.product;
    if (!product || product.id !== productId) {
      return null;
    }

    return {
      value: String(product.id),
      label: `${product.code} - ${product.name}`,
    };
  }

  private toInvoiceApplicationOption(application: DocApplicationInvoice): ZardComboboxOption {
    return {
      value: String(application.id),
      label: `#${application.id} \u00b7 ${application.customer?.fullName ?? 'Unknown customer'}`,
    };
  }

  private findPendingApplicationById(applicationId: number): DocApplicationInvoice | undefined {
    return this.findAvailableApplicationById(applicationId);
  }

  private resolveProductPrice(productId: number | null | undefined): number {
    if (!productId) {
      return 0;
    }
    const row = this.findBillableProduct(productId);
    return resolveProductPriceFromProduct(row?.product);
  }

  private resolveApplicationPrice(app: DocApplicationInvoice): number {
    return resolveProductPriceFromProduct(app.product as Product);
  }

  private getLineQuantity(group: FormGroup): number {
    return this.normalizeLineQuantity(group.get('quantity')?.value);
  }

  private normalizeLineQuantity(value: unknown): number {
    const quantity = Number(value ?? 1);
    if (!Number.isFinite(quantity)) {
      return 1;
    }
    return Math.max(1, Math.trunc(quantity));
  }

  private normalizeLineNotes(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    return value.trim() ? value : null;
  }

  private updateLineAmountFromDefault(group: FormGroup): void {
    if (group.get('amountOverridden')?.value) {
      return;
    }

    const quantity = this.getLineQuantity(group);
    const application = this.resolveLineApplication(group);
    if (application) {
      group
        .get('amount')
        ?.setValue(this.resolveApplicationPrice(application) * quantity, { emitEvent: false });
      this.updateTotalAmount();
      return;
    }

    const productId = this.resolveLineProductId(group);
    group
      .get('amount')
      ?.setValue(this.resolveProductPrice(productId) * quantity, { emitEvent: false });
    this.updateTotalAmount();
  }

  private updateTotalAmount(): void {
    const invoiceApplications = this.form?.get?.('invoiceApplications');
    if (!(invoiceApplications instanceof FormArray)) {
      return;
    }

    const total = invoiceApplications.controls.reduce((sum, group) => {
      const amount = Number(group.get('amount')?.value ?? 0);
      return sum + (Number.isNaN(amount) ? 0 : amount);
    }, 0);
    this.totalAmount.set(total);
  }

  private loadFromApplication(applicationId: number): void {
    this.isLoading.set(true);

    this.invoicesApi.invoicesFromApplicationPrefillRetrieve({ applicationId }).subscribe({
      next: (response) => {
        const payload = unwrapApiRecord(response) as Record<string, any> | null;
        const customerId = payload?.['customer']?.id ?? null;
        const sourceLine = payload?.['invoiceApplication'] ?? null;
        const sourceApplicationId = sourceLine?.['customerApplication'] ?? null;
        const sourceProductId = sourceLine?.['product'] ?? null;

        if (!customerId || !sourceProductId || !sourceApplicationId) {
          this.toast.error('Invalid source application prefill payload.');
          this.addLineItem({}, { manual: false });
          this.isLoading.set(false);
          return;
        }

        this.lockCustomerFromSource.set(true);
        this.form.get('customer')?.setValue(customerId, { emitEvent: false });
        this.form.get('customer')?.disable({ emitEvent: false });

        this.fetchBillableProducts(customerId).subscribe({
          next: (rows: BillableProductRow[]) => {
            this.billableProducts.set(rows);
            this.invoiceApplications.clear();
            this.addLineItem(
              {
                product: Number(sourceProductId),
                customerApplication: Number(sourceApplicationId),
                quantity: Number(sourceLine['quantity'] ?? 1),
                notes: sourceLine['notes'] ?? '',
                amount: Number(sourceLine['amount'] ?? 0),
                amountOverridden: false,
                identityLocked: true,
              },
              { manual: false },
            );
            this.isLoading.set(false);
            this.cdr.markForCheck();
          },
          error: (error: unknown) => {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message
                ? `Failed to load billable products: ${message}`
                : 'Failed to load billable products',
            );
            this.invoiceApplications.clear();
            this.addLineItem({}, { manual: false });
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
        this.addLineItem({}, { manual: false });
        this.isLoading.set(false);
      },
    });
  }

  private loadInvoice(id: number): void {
    this.isLoading.set(true);
    this.invoicesApi.invoicesRetrieve({ id }).subscribe({
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
          this.addLineItem({}, { manual: false });
          this.isLoading.set(false);
          return;
        }

        this.fetchBillableProducts(customerId, invoice.id).subscribe({
          next: (rows: BillableProductRow[]) => {
            this.billableProducts.set(rows);
            this.invoiceApplications.clear();

            for (const item of invoice.invoiceApplications ?? []) {
              const productId = item.product?.id ?? item.customerApplication?.product?.id ?? null;
              this.addLineItem(
                {
                  id: item.id,
                  product: productId,
                  customerApplication: item.customerApplication?.id ?? null,
                  quantity: Number(item.quantity ?? 1),
                  notes: item.notes ?? '',
                  amount: Number(item.amount ?? 0),
                  amountOverridden: true,
                  identityLocked: true,
                },
                { manual: false },
              );
            }

            if ((invoice.invoiceApplications ?? []).length === 0) {
              this.addLineItem({}, { manual: false });
            }

            this.isLoading.set(false);
            this.cdr.markForCheck();
          },
          error: (error: unknown) => {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message
                ? `Failed to load billable products: ${message}`
                : 'Failed to load billable products',
            );
            this.invoiceApplications.clear();
            this.addLineItem({}, { manual: false });
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
      next: (rows: BillableProductRow[]) => {
        this.billableProducts.set(rows);
        this.cdr.markForCheck();
      },
      error: (error: unknown) => {
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
      .invoicesGetBillableProductsList({ customerId, currentInvoiceId })
      .pipe(map((rows) => normalizeBillableRows(rows)));
  }

  private proposeInvoiceNo(invoiceDate?: Date | string | null): void {
    if (!invoiceDate) return;
    const date = invoiceDate instanceof Date ? invoiceDate : new Date(invoiceDate);
    if (Number.isNaN(date.getTime())) return;

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const dateStr = `${year}-${month}-${day}`;

    this.invoicesApi.invoicesProposeRetrieve({ invoiceDate: dateStr }).subscribe({
      next: (res) => {
        const ctrl = this.form.get('invoiceNo');
        if (ctrl && !ctrl.dirty) {
          const payload = unwrapApiRecord(res) as { invoiceNo?: number | string } | null;
          const proposedNo = payload?.invoiceNo;
          if (proposedNo) {
            ctrl.setValue(Number(proposedNo), { emitEvent: false });
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
