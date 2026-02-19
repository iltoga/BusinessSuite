import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  effect,
  inject,
  input,
  output,
  signal,
  viewChild,
  type TemplateRef,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { forkJoin } from 'rxjs';

import { PaymentsService, type InvoiceApplicationDetail, type Payment } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { ZardDialogService } from '@/shared/components/dialog';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardInputDirective } from '@/shared/components/input';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-payment-modal',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardButtonComponent,
    ZardDateInputComponent,
    ZardInputDirective,
    FormErrorSummaryComponent,
  ],
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
  readonly invoiceApplications = input<InvoiceApplicationDetail[] | null>(null);
  readonly payment = input<Payment | null>(null);
  readonly saved = output<void>();
  readonly closed = output<void>();

  private dialogRef = signal<ReturnType<ZardDialogService['create']> | null>(null);

  readonly contentTemplate = viewChild.required<TemplateRef<unknown>>('contentTemplate');

  readonly isSaving = signal(false);

  readonly isEditMode = computed(() => !!this.payment());
  readonly fullPaymentApplications = computed(() =>
    (this.invoiceApplications() ?? []).filter((app) => Number(app.dueAmount ?? 0) > 0),
  );
  readonly isFullPaymentMode = computed(
    () => !this.isEditMode() && this.fullPaymentApplications().length > 1,
  );
  readonly modalTitle = computed(() => {
    if (this.isEditMode()) {
      return 'Edit Payment';
    }
    return this.isFullPaymentMode() ? 'Record Full Payment' : 'Record Payment';
  });
  readonly submitLabel = computed(() => (this.isEditMode() ? 'Save Changes' : 'Record Payment'));
  readonly maxEditableAmount = computed(() => {
    if (this.isFullPaymentMode()) {
      return this.fullPaymentApplications().reduce(
        (sum, app) => sum + Number(app.dueAmount ?? 0),
        0,
      );
    }

    const app = this.invoiceApplication();
    if (!app) {
      return 0;
    }

    const due = Number(app.dueAmount ?? 0);
    const currentPayment = this.payment();
    const currentAmount = currentPayment ? Number(currentPayment.amount ?? 0) : 0;

    return due + currentAmount;
  });

  readonly form = this.fb.group({
    paymentDate: [this.todayLocalDate(), Validators.required],
    paymentType: ['cash', Validators.required],
    amount: [0, [Validators.required, Validators.min(1)]],
    notes: [''],
  });

  readonly formErrorLabels: Record<string, string> = {
    paymentDate: 'Payment Date',
    paymentType: 'Payment Type',
    amount: 'Amount',
    notes: 'Notes',
  };

  constructor() {
    effect(() => {
      const open = this.isOpen();
      const current = this.dialogRef();

      if (open && !current) {
        this.prefillForm();

        const ref = this.dialogService.create({
          zTitle: this.modalTitle(),
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
        this.resetForm();
      }
    });

    this.destroyRef.onDestroy(() => {
      const current = this.dialogRef();
      if (current) {
        current.close();
      }
    });
  }

  private resetForm(): void {
    this.form.reset({
      paymentDate: this.todayLocalDate(),
      paymentType: 'cash',
      amount: 0,
      notes: '',
    });
    this.form.controls.amount.enable({ emitEvent: false });
  }

  private prefillForm(): void {
    const app = this.invoiceApplication();
    const payment = this.payment();
    const defaultDate = this.todayLocalDate();

    if (payment) {
      this.form.controls.amount.enable({ emitEvent: false });
      this.form.patchValue({
        paymentDate: this.parseApiDate(payment.paymentDate) ?? defaultDate,
        paymentType: payment.paymentType ?? 'cash',
        amount: Number(payment.amount ?? 0),
        notes: payment.notes ?? '',
      });
      return;
    }

    if (this.isFullPaymentMode()) {
      this.form.patchValue({
        amount: this.maxEditableAmount(),
        paymentDate: defaultDate,
        paymentType: 'cash',
        notes: '',
      });
      this.form.controls.amount.disable({ emitEvent: false });
      return;
    }

    this.form.controls.amount.enable({ emitEvent: false });
    if (app) {
      this.form.patchValue({
        amount: Number(app.dueAmount ?? 0),
        paymentDate: defaultDate,
        paymentType: 'cash',
        notes: '',
      });
    } else {
      this.resetForm();
    }
  }

  submit(): void {
    if (this.form.invalid) {
      return;
    }

    const payment = this.payment();
    const raw = this.form.getRawValue();
    const amount = Number(raw.amount ?? 0);
    const maxAllowed = this.maxEditableAmount();
    const paymentType = this.normalizePaymentType(raw.paymentType);

    if (amount > maxAllowed || amount <= 0) {
      this.toast.error('Payment amount exceeds the allowed amount.');
      return;
    }

    this.isSaving.set(true);
    const paymentDate = this.toApiDate(raw.paymentDate);
    if (!paymentDate) {
      this.toast.error('Invalid payment date.');
      this.isSaving.set(false);
      return;
    }

    if (this.isFullPaymentMode()) {
      this.submitFullPayment(paymentDate, paymentType, raw.notes ?? '');
      return;
    }

    const app = this.invoiceApplication();
    const invoiceApplicationId = app?.id ?? payment?.invoiceApplication;
    if (!invoiceApplicationId) {
      this.toast.error('Unable to locate invoice application for this payment.');
      this.isSaving.set(false);
      return;
    }

    const payload = {
      invoiceApplication: invoiceApplicationId,
      paymentDate,
      paymentType,
      amount: String(amount),
      notes: raw.notes ?? '',
    } as Payment;

    const request$ = payment
      ? this.paymentsApi.paymentsUpdate(payment.id, payload)
      : this.paymentsApi.paymentsCreate(payload);

    request$.subscribe({
      next: () => {
        this.toast.success(payment ? 'Payment updated' : 'Payment recorded');
        this.saved.emit();
        this.isSaving.set(false);
      },
      error: (error) => {
        applyServerErrorsToForm(this.form, error);
        this.form.markAllAsTouched();
        const message = extractServerErrorMessage(error);
        const fallback = payment ? 'Failed to update payment' : 'Failed to record payment';
        this.toast.error(message ? `${fallback}: ${message}` : fallback);
        this.isSaving.set(false);
      },
    });
  }

  private submitFullPayment(
    paymentDate: string,
    paymentType: Payment.PaymentTypeEnum,
    notes: string,
  ): void {
    const applications = this.fullPaymentApplications();
    if (applications.length < 2) {
      this.toast.error(
        'Full payment is available only when multiple applications have outstanding due.',
      );
      this.isSaving.set(false);
      return;
    }

    const requests = applications.map((application) =>
      this.paymentsApi.paymentsCreate({
        invoiceApplication: application.id,
        paymentDate,
        paymentType,
        amount: String(Number(application.dueAmount ?? 0)),
        notes,
      } as Payment),
    );

    forkJoin(requests).subscribe({
      next: () => {
        this.toast.success(
          applications.length === 1
            ? 'Payment recorded'
            : `${applications.length} payments recorded`,
        );
        this.saved.emit();
        this.isSaving.set(false);
      },
      error: (error) => {
        applyServerErrorsToForm(this.form, error);
        this.form.markAllAsTouched();
        const message = extractServerErrorMessage(error);
        const fallback = 'Failed to record full payment';
        this.toast.error(message ? `${fallback}: ${message}` : fallback);
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

  getFullPaymentApplicationCount(): number {
    return this.fullPaymentApplications().length;
  }

  close(): void {
    this.closed.emit();
  }

  private todayLocalDate(): Date {
    const now = new Date();
    return new Date(now.getFullYear(), now.getMonth(), now.getDate());
  }

  private toApiDate(value: unknown): string | null {
    const parsed = this.parseApiDate(value);
    if (!parsed) {
      return null;
    }
    const year = parsed.getFullYear();
    const month = String(parsed.getMonth() + 1).padStart(2, '0');
    const day = String(parsed.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private normalizePaymentType(value: unknown): Payment.PaymentTypeEnum {
    switch (value) {
      case 'credit_card':
      case 'wire_transfer':
      case 'crypto':
      case 'paypal':
      case 'cash':
        return value;
      default:
        return 'cash';
    }
  }

  private parseApiDate(value: unknown): Date | null {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }
    if (typeof value !== 'string') {
      return null;
    }
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
}
