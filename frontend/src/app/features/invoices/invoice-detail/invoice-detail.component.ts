import { CommonModule, formatDate, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  HostListener,
  LOCALE_ID,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  InvoicesService,
  PaymentsService,
  type InvoiceApplicationDetail,
  type InvoiceDetail,
  type Payment,
} from '@/core/api';
import { ConfigService } from '@/core/services/config.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ConfirmDialogComponent } from '@/shared/components/confirm-dialog/confirm-dialog.component';
import { InvoiceDownloadDropdownComponent } from '@/shared/components/invoice-download-dropdown/invoice-download-dropdown.component';
import {
  CardSkeletonComponent,
  TableSkeletonComponent,
  ZardSkeletonComponent,
} from '@/shared/components/skeleton';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { PaymentModalComponent } from '../payment-modal/payment-modal.component';

@Component({
  selector: 'app-invoice-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ConfirmDialogComponent,
    PaymentModalComponent,
    CardSkeletonComponent,
    TableSkeletonComponent,
    ZardSkeletonComponent,
    InvoiceDownloadDropdownComponent,
    AppDatePipe,
    ...ZardTooltipImports,
  ],
  templateUrl: './invoice-detail.component.html',
  styleUrls: ['./invoice-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private invoicesApi = inject(InvoicesService);
  private paymentsApi = inject(PaymentsService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);
  private locale = inject(LOCALE_ID);
  private configService = inject(ConfigService);

  readonly invoice = signal<InvoiceDetail | null>(null);
  readonly isLoading = signal(false);
  readonly originSearchQuery = signal<string | null>(null);
  readonly paymentModalOpen = signal(false);
  readonly selectedApplication = signal<InvoiceApplicationDetail | null>(null);
  readonly selectedPayment = signal<Payment | null>(null);
  readonly paymentDeleteOpen = signal(false);
  readonly paymentToDelete = signal<Payment | null>(null);
  readonly isDeletingPayment = signal(false);

  readonly totalDue = computed(() => this.invoice()?.totalDueAmount ?? 0);
  readonly deletePaymentMessage = computed(() => {
    const payment = this.paymentToDelete();
    if (!payment) {
      return 'Are you sure you want to delete this payment?';
    }

    const amount = this.formatCurrency(payment.amount);
    const date = this.formatDateForDisplay(payment.paymentDate);
    return `Delete payment of ${amount} dated ${date}? This will update invoice totals.`;
  });

  goBack(): void {
    const st = history.state as any;
    const invoice = this.invoice();

    const focusState: Record<string, unknown> = {
      focusTable: true,
      focusId: invoice?.id,
      searchQuery: this.originSearchQuery(),
    };

    if (st?.from === 'applications') {
      this.router.navigate(['/applications'], { state: focusState });
      return;
    }

    this.router.navigate(['/invoices'], { state: focusState });
  }

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    const invoice = this.invoice();
    if (!invoice) return;

    // E --> Edit
    if (event.key === 'E' && !event.ctrlKey && !event.altKey && !event.metaKey) {
      event.preventDefault();
      this.router.navigate(['/invoices', invoice.id, 'edit'], {
        state: {
          from: history.state?.from,
          focusId: invoice.id,
          searchQuery: this.originSearchQuery(),
        },
      });
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
    }
  }

  hasDue(app: InvoiceApplicationDetail): boolean {
    return Number(app.dueAmount) > 0;
  }

  getApplicationProductCode(app: InvoiceApplicationDetail): string {
    const customerApplication = app.customerApplication as unknown as {
      product?: { code?: string | null } | null;
    };
    return customerApplication?.product?.code ?? '—';
  }

  getApplicationProductName(app: InvoiceApplicationDetail): string {
    const customerApplication = app.customerApplication as unknown as {
      product?: { name?: string | null } | null;
    };
    return customerApplication?.product?.name ?? '—';
  }

  getApplicationCustomerName(app: InvoiceApplicationDetail): string {
    const customerApplication = app.customerApplication as unknown as {
      customer?: { fullName?: string | null } | null;
    };
    return customerApplication?.customer?.fullName ?? '—';
  }

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }
    const st = (window as any).history.state || {};
    this.originSearchQuery.set(st.searchQuery ?? null);

    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.loadInvoice(Number(idParam));
    }
  }

  openPaymentModal(app: InvoiceApplicationDetail): void {
    this.selectedApplication.set(app);
    this.selectedPayment.set(null);
    this.paymentModalOpen.set(true);
  }

  openEditPaymentModal(app: InvoiceApplicationDetail, payment: Payment): void {
    this.selectedApplication.set(app);
    this.selectedPayment.set(payment);
    this.paymentModalOpen.set(true);
  }

  requestDeletePayment(payment: Payment): void {
    this.paymentToDelete.set(payment);
    this.paymentDeleteOpen.set(true);
  }

  cancelDeletePayment(): void {
    this.paymentDeleteOpen.set(false);
    this.paymentToDelete.set(null);
  }

  confirmDeletePayment(): void {
    const payment = this.paymentToDelete();
    if (!payment || this.isDeletingPayment()) {
      return;
    }

    this.isDeletingPayment.set(true);

    this.paymentsApi.paymentsDestroy(payment.id).subscribe({
      next: () => {
        this.toast.success('Payment deleted');
        this.isDeletingPayment.set(false);
        this.paymentDeleteOpen.set(false);
        this.paymentToDelete.set(null);

        const id = this.invoice()?.id;
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

  closePaymentModal(): void {
    this.paymentModalOpen.set(false);
    this.selectedApplication.set(null);
    this.selectedPayment.set(null);
  }

  onPaymentSaved(): void {
    const id = this.invoice()?.id;
    if (id) {
      this.loadInvoice(id);
    }
    this.closePaymentModal();
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

  paymentStatusVariant(
    status?: string | null,
  ): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
    return this.statusVariant(status);
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

  private formatDateForDisplay(value: string | null | undefined): string {
    if (!value) {
      return '—';
    }
    const parsed = this.parseApiDate(value);
    if (!parsed) {
      return value;
    }
    return formatDate(
      parsed,
      this.normalizeDateFormat(this.configService.settings.dateFormat),
      this.locale,
    );
  }

  private parseApiDate(value: string): Date | null {
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const match = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (!match) {
      const parsed = new Date(trimmed);
      if (Number.isNaN(parsed.getTime())) {
        return null;
      }
      return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return date;
  }

  private normalizeDateFormat(format: string | null | undefined): string {
    const normalized = (format ?? '').trim();
    if (['dd-MM-yyyy', 'yyyy-MM-dd', 'dd/MM/yyyy', 'MM/dd/yyyy'].includes(normalized)) {
      return normalized;
    }
    return 'dd-MM-yyyy';
  }

  private loadInvoice(id: number): void {
    this.isLoading.set(true);
    this.invoicesApi.invoicesRetrieve(id).subscribe({
      next: (invoice: InvoiceDetail) => {
        this.invoice.set(invoice);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load invoice');
        this.isLoading.set(false);
      },
    });
  }
}
