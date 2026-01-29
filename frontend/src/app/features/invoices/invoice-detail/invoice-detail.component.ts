import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';

import { InvoicesService, type InvoiceApplicationDetail, type InvoiceDetail } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
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
    PaymentModalComponent,
  ],
  templateUrl: './invoice-detail.component.html',
  styleUrls: ['./invoice-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private invoicesApi = inject(InvoicesService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);

  readonly invoice = signal<InvoiceDetail | null>(null);
  readonly isLoading = signal(false);
  readonly paymentModalOpen = signal(false);
  readonly selectedApplication = signal<InvoiceApplicationDetail | null>(null);

  readonly totalDue = computed(() => this.invoice()?.totalDueAmount ?? 0);

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

    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.loadInvoice(Number(idParam));
    }
  }

  openPaymentModal(app: InvoiceApplicationDetail): void {
    this.selectedApplication.set(app);
    this.paymentModalOpen.set(true);
  }

  closePaymentModal(): void {
    this.paymentModalOpen.set(false);
    this.selectedApplication.set(null);
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
