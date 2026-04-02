import { formatDate as angularFormatDate } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  LOCALE_ID,
  computed,
  inject,
  signal,
  viewChild,
} from '@angular/core';
import { Observable } from 'rxjs';

import {
  InvoicesService,
  PaymentsService,
  type InvoiceApplicationDetail,
  type InvoiceDetail,
  type Payment,
} from '@/core/api';
import { ConfigService } from '@/core/services/config.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { CardSectionComponent } from '@/shared/components/card-section';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import { DetailFieldComponent } from '@/shared/components/detail-field';
import { ZardDropdownImports } from '@/shared/components/dropdown';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { InvoiceDownloadDropdownComponent } from '@/shared/components/invoice-download-dropdown/invoice-download-dropdown.component';
import { CardSkeletonComponent, ZardSkeletonComponent } from '@/shared/components/skeleton';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { BaseDetailComponent, BaseDetailConfig } from '@/shared/core/base-detail.component';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { formatDateForDisplay } from '@/shared/utils/date-parsing';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { PaymentModalComponent } from '../payment-modal/payment-modal.component';

/**
 * Invoice detail component
 *
 * Extends BaseDetailComponent to inherit common detail view patterns:
 * - Keyboard shortcuts (E for edit, D for delete, B/Left for back)
 * - Navigation state management (returnUrl, searchQuery, page)
 * - Loading states
 * - Delete confirmation
 */
@Component({
  selector: 'app-invoice-detail',
  standalone: true,
  imports: [
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    CardSectionComponent,
    DetailFieldComponent,
    ConfirmDialogComponent,
    PaymentModalComponent,
    CardSkeletonComponent,
    ZardSkeletonComponent,
    InvoiceDownloadDropdownComponent,
    ZardIconComponent,
    AppDatePipe,
    ...ZardTooltipImports,
    ...ZardDropdownImports,
  ],
  templateUrl: './invoice-detail.component.html',
  styleUrls: ['./invoice-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDetailComponent extends BaseDetailComponent<InvoiceDetail> {
  private readonly invoicesApi = inject(InvoicesService);
  private readonly paymentsApi = inject(PaymentsService);
  private readonly locale = inject(LOCALE_ID);
  private readonly configService = inject(ConfigService);

  // Expose item as invoice for template compatibility
  get invoice() {
    return this.item;
  }

  // Invoice-specific state
  readonly paymentModalOpen = signal(false);
  readonly selectedApplication = signal<InvoiceApplicationDetail | null>(null);
  readonly selectedApplications = signal<InvoiceApplicationDetail[]>([]);
  readonly selectedPayment = signal<Payment | null>(null);
  readonly paymentDeleteOpen = signal(false);
  readonly paymentToDelete = signal<Payment | null>(null);
  readonly isDeletingPayment = signal(false);
  private readonly downloadDropdown = viewChild(InvoiceDownloadDropdownComponent);

  // Computed properties
  readonly totalDue = computed(() => this.item()?.totalDueAmount ?? 0);
  readonly dueApplications = computed(() =>
    (this.item()?.invoiceApplications ?? []).filter((app) => this.hasDue(app)),
  );
  readonly hasMultipleDueApplications = computed(() => this.dueApplications().length > 1);
  readonly deletePaymentMessage = computed(() => {
    const payment = this.paymentToDelete();
    if (!payment) {
      return 'Are you sure you want to delete this payment?';
    }

    const amount = this.formatCurrency(payment.amount);
    const date = this.displayDate(payment.paymentDate);
    return `Delete payment of ${amount} dated ${date}? This will update invoice totals.`;
  });

  constructor() {
    super();
    this.config = {
      entityType: 'invoices',
      entityLabel: 'Invoice',
      enableDelete: false, // Invoice delete handled differently
    } as BaseDetailConfig<InvoiceDetail>;
  }

  /**
   * Load invoice from service
   */
  protected override loadItem(id: number): Observable<InvoiceDetail> {
    return this.invoicesApi.invoicesRetrieve({ id });
  }

  /**
   * Delete invoice - not implemented in base, handled separately
   */
  protected override deleteItem(id: number): Observable<any> {
    // Invoice deletion is more complex and handled via dialog
    // This is a placeholder to satisfy the base class contract
    throw new Error('Invoice deletion requires special handling');
  }

  /**
   * Initialize component
   */
  override ngOnInit(): void {
    if (!this.isBrowser) return;

    this.restoreNavigationState();

    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.loadInvoice(Number(idParam));
    }
  }

  /**
   * Handle keyboard shortcuts
   */
  override handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;
    if (event.repeat) return;

    const invoice = this.item();
    if (!invoice) return;

    // E --> Edit
    if (event.key === 'E' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.onEdit();
    }

    // B or Left Arrow --> Back to list
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.goBack();
      return;
    }

    // P (without Shift) --> Print Preview from invoice download control
    if (
      !event.shiftKey &&
      event.key.toLowerCase() === 'p' &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      const dropdown = this.downloadDropdown();
      if (!dropdown) {
        return;
      }

      event.preventDefault();
      dropdown.openPrintPreview();
    }
  }

  /**
   * Navigate to edit invoice
   */
  onEdit(): void {
    const invoice = this.item();
    if (!invoice) return;
    this.router.navigate(['/invoices', invoice.id, 'edit'], {
      state: {
        from: history.state?.from,
        customerId: history.state?.customerId,
        returnUrl: history.state?.returnUrl,
        focusId: invoice.id,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
      },
    });
  }

  /**
   * Check if application has due amount
   */
  hasDue(app: InvoiceApplicationDetail): boolean {
    return Number(app.dueAmount) > 0;
  }

  /**
   * Get application product code
   */
  getApplicationProductCode(app: InvoiceApplicationDetail): string {
    const lineProduct = app.product as { code?: string | null } | null;
    const customerApplication = app.customerApplication as {
      product?: { code?: string | null } | null;
    } | null;
    return lineProduct?.code ?? customerApplication?.product?.code ?? '—';
  }

  /**
   * Get application product name
   */
  getApplicationProductName(app: InvoiceApplicationDetail): string {
    const lineProduct = app.product as { name?: string | null } | null;
    const customerApplication = app.customerApplication as {
      product?: { name?: string | null } | null;
    } | null;
    return lineProduct?.name ?? customerApplication?.product?.name ?? '—';
  }

  /**
   * Get application customer name
   */
  getApplicationCustomerName(app: InvoiceApplicationDetail): string | null {
    const customerApplication = app.customerApplication as {
      customer?: { fullName?: string | null } | null;
    } | null;
    return customerApplication?.customer?.fullName ?? null;
  }

  getApplicationQuantity(app: InvoiceApplicationDetail): number {
    const quantity = Number(app.quantity ?? 1);
    return Number.isFinite(quantity) && quantity > 0 ? Math.trunc(quantity) : 1;
  }

  getApplicationNotes(app: InvoiceApplicationDetail): string | null {
    const notes = app.notes;
    return typeof notes === 'string' && notes.trim() ? notes : null;
  }

  /**
   * Open linked application
   */
  openLinkedApplication(applicationId: number): void {
    const invoiceId = this.item()?.id;
    if (!invoiceId || !applicationId) {
      return;
    }

    const returnUrl = this.router.url.startsWith('/') ? this.router.url : `/invoices/${invoiceId}`;
    this.router.navigate(['/applications', applicationId], {
      state: {
        from: 'invoices',
        returnUrl,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
        focusId: applicationId,
      },
    });
  }

  /**
   * Open payment modal for application
   */
  openPaymentModal(app: InvoiceApplicationDetail): void {
    this.selectedApplication.set(app);
    this.selectedApplications.set([]);
    this.selectedPayment.set(null);
    this.paymentModalOpen.set(true);
  }

  /**
   * Open full payment modal for all due applications
   */
  openFullPaymentModal(): void {
    this.selectedApplication.set(null);
    this.selectedApplications.set(this.dueApplications());
    this.selectedPayment.set(null);
    this.paymentModalOpen.set(true);
  }

  /**
   * Open edit payment modal
   */
  openEditPaymentModal(app: InvoiceApplicationDetail, payment: Payment): void {
    this.selectedApplication.set(app);
    this.selectedApplications.set([]);
    this.selectedPayment.set(payment);
    this.paymentModalOpen.set(true);
  }

  /**
   * Request delete payment
   */
  requestDeletePayment(payment: Payment): void {
    this.paymentToDelete.set(payment);
    this.paymentDeleteOpen.set(true);
  }

  /**
   * Cancel delete payment
   */
  cancelDeletePayment(): void {
    this.paymentDeleteOpen.set(false);
    this.paymentToDelete.set(null);
  }

  /**
   * Confirm delete payment
   */
  confirmDeletePayment(): void {
    const payment = this.paymentToDelete();
    if (!payment || this.isDeletingPayment()) {
      return;
    }

    this.isDeletingPayment.set(true);

    this.paymentsApi.paymentsDestroy({ id: payment.id }).subscribe({
      next: () => {
        this.toast.success('Payment deleted');
        this.isDeletingPayment.set(false);
        this.paymentDeleteOpen.set(false);
        this.paymentToDelete.set(null);

        const id = this.item()?.id;
        if (id) {
          this.loadInvoice(id);
        }
      },
      error: (error) => {
        const message = extractServerErrorMessage(error);
        this.toast.error(
          message ? `Failed to delete payment: ${message}` : 'Failed to delete payment',
        );
        this.isDeletingPayment.set(false);
        this.paymentDeleteOpen.set(false);
        this.paymentToDelete.set(null);
      },
    });
  }

  /**
   * Close payment modal
   */
  closePaymentModal(): void {
    this.paymentModalOpen.set(false);
    this.selectedApplication.set(null);
    this.selectedApplications.set([]);
    this.selectedPayment.set(null);
  }

  /**
   * Handle payment saved
   */
  onPaymentSaved(): void {
    const id = this.item()?.id;
    if (id) {
      this.loadInvoice(id);
    }
    this.closePaymentModal();
  }

  /**
   * Get status badge variant
   */
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

  /**
   * Get payment status variant
   */
  paymentStatusVariant(
    status?: string | null,
  ): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
    return this.statusVariant(status);
  }

  /**
   * Format currency value
   */
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

  /**
   * Load invoice
   */
  private loadInvoice(id: number): void {
    this.isLoading.set(true);
    this.invoicesApi.invoicesRetrieve({ id }).subscribe({
      next: (invoice: InvoiceDetail) => {
        this.item.set(invoice);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load invoice');
        this.isLoading.set(false);
      },
    });
  }

  /**
   * Format date for display — delegates to shared utility
   */
  private displayDate(value: string | null | undefined): string {
    return formatDateForDisplay(
      value,
      angularFormatDate,
      this.configService.settings.dateFormat,
      this.locale,
    );
  }
}
