import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
  type TemplateRef,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';

import { PaymentsService, type InvoiceApplicationDetail, type Payment } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-payment-modal',
  standalone: true,
  imports: [CommonModule, ReactiveFormsModule, ZardButtonComponent, ZardInputDirective],
  templateUrl: './payment-modal.component.html',
  styleUrls: ['./payment-modal.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PaymentModalComponent {
  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);
  private fb = inject(FormBuilder);
  private paymentsApi = inject(PaymentsService);
  private toast = inject(GlobalToastService);

  readonly isOpen = input<boolean>(false);
  readonly invoiceApplication = input<InvoiceApplicationDetail | null>(null);
  readonly saved = output<Payment>();
  readonly closed = output<void>();

  private dialogRef = signal<ReturnType<ZardDialogService['create']> | null>(null);

  readonly contentTemplate = viewChild.required<TemplateRef<unknown>>('contentTemplate');

  readonly isSaving = signal(false);

  readonly form = this.fb.group({
    paymentDate: [new Date().toISOString().split('T')[0], Validators.required],
    paymentType: ['cash', Validators.required],
    amount: [0, [Validators.required, Validators.min(1)]],
    notes: [''],
  });

  constructor() {
    effect(() => {
      const open = this.isOpen();
      const current = this.dialogRef();

      if (open && !current) {
        const app = this.invoiceApplication();
        if (app) {
          this.form.patchValue({
            amount: Number(app.dueAmount ?? 0),
            paymentDate: new Date().toISOString().split('T')[0],
          });
        }

        const ref = this.dialogService.create({
          zTitle: 'Record Payment',
          zContent: this.contentTemplate(),
          zHideFooter: true,
          zClosable: true,
          zOnCancel: () => {
            this.closed.emit();
          },
        });
        this.dialogRef.set(ref);
      }

      if (!open && current) {
        current.close();
        this.dialogRef.set(null);
      }
    });

    this.destroyRef.onDestroy(() => {
      const current = this.dialogRef();
      if (current) {
        current.close();
      }
    });
  }

  submit(): void {
    if (this.form.invalid || !this.invoiceApplication()) {
      return;
    }

    const app = this.invoiceApplication()!;
    const raw = this.form.getRawValue();
    const amount = Number(raw.amount ?? 0);
    const due = Number(app.dueAmount ?? 0);

    if (amount > due) {
      this.toast.error('Payment amount exceeds the due amount.');
      return;
    }

    this.isSaving.set(true);

    this.paymentsApi
      .paymentsCreate({
        invoiceApplication: app.id,
        paymentDate: raw.paymentDate,
        paymentType: raw.paymentType,
        amount: String(amount),
        notes: raw.notes ?? '',
      } as Payment)
      .subscribe({
        next: (payment: Payment) => {
          this.toast.success('Payment recorded');
          this.saved.emit(payment);
          this.isSaving.set(false);
        },
        error: () => {
          this.toast.error('Failed to record payment');
          this.isSaving.set(false);
        },
      });
  }

  getApplicationProductCode(): string {
    const invoiceApplication = this.invoiceApplication();
    if (!invoiceApplication) {
      return '—';
    }
    const customerApplication = invoiceApplication.customerApplication as unknown as {
      product?: { code?: string | null } | null;
    };
    return customerApplication?.product?.code ?? '—';
  }

  getApplicationProductName(): string {
    const invoiceApplication = this.invoiceApplication();
    if (!invoiceApplication) {
      return '—';
    }
    const customerApplication = invoiceApplication.customerApplication as unknown as {
      product?: { name?: string | null } | null;
    };
    return customerApplication?.product?.name ?? '—';
  }

  getApplicationCustomerName(): string {
    const invoiceApplication = this.invoiceApplication();
    if (!invoiceApplication) {
      return '—';
    }
    const customerApplication = invoiceApplication.customerApplication as unknown as {
      customer?: { fullName?: string | null } | null;
    };
    return customerApplication?.customer?.fullName ?? '—';
  }

  close(): void {
    this.closed.emit();
  }
}
