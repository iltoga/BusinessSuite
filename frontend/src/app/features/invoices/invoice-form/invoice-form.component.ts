import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  ChangeDetectorRef,
  Component,
  PLATFORM_ID,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { FormArray, FormBuilder, FormGroup, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  CustomerApplicationsService,
  InvoicesService,
  type DocApplicationInvoice,
  type InvoiceCreateUpdate,
  type InvoiceDetail,
  type PaginatedDocApplicationInvoiceList,
} from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { CustomerSelectComponent } from '@/shared/components/customer-select/customer-select.component';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { ZardInputDirective } from '@/shared/components/input';

@Component({
  selector: 'app-invoice-form',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardButtonComponent,
    ZardCardComponent,
    ZardDateInputComponent,
    CustomerSelectComponent,
  ],
  templateUrl: './invoice-form.component.html',
  styleUrls: ['./invoice-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private invoicesApi = inject(InvoicesService);
  private applicationsApi = inject(CustomerApplicationsService);
  private toast = inject(GlobalToastService);
  private platformId = inject(PLATFORM_ID);
  private http = inject(HttpClient);
  private cdr = inject(ChangeDetectorRef);

  readonly isLoading = signal(false);
  readonly isSaving = signal(false);
  readonly isEditMode = signal(false);
  readonly invoice = signal<InvoiceDetail | null>(null);
  readonly customerApplications = signal<DocApplicationInvoice[]>([]);

  readonly form = this.fb.group({
    customer: [null as number | null, Validators.required],
    invoiceNo: [null as number | null],
    invoiceDate: [new Date(), Validators.required],
    dueDate: [new Date(), Validators.required],
    notes: [''],
    sent: [false],
    invoiceApplications: this.fb.array<FormGroup>([]),
  });

  readonly totalAmount = computed(() => {
    const items = this.invoiceApplications.controls;
    return items.reduce((sum, group) => {
      const amount = Number(group.get('amount')?.value ?? 0);
      return sum + (Number.isNaN(amount) ? 0 : amount);
    }, 0);
  });

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
    } else {
      if (applicationId) {
        this.loadFromApplication(Number(applicationId));
      } else {
        this.addLineItem();
      }

      // For new invoices, propose an invoice number based on invoice date
      this.proposeInvoiceNo(this.form.get('invoiceDate')?.value);

      this.form.get('invoiceDate')?.valueChanges.subscribe((value) => {
        // Only propose when creating, and don't overwrite if user already edited invoiceNo
        if (this.isEditMode()) return;
        const invoiceNoCtrl = this.form.get('invoiceNo');
        if (invoiceNoCtrl && !invoiceNoCtrl.dirty) {
          this.proposeInvoiceNo(value);
        }
      });
    }

    const customerId = this.form.get('customer')?.value;
    if (customerId) {
      this.loadCustomerApplications(customerId);
    }

    this.form.get('customer')?.valueChanges.subscribe((value) => {
      if (this.isEditMode()) {
        return;
      }
      if (value) {
        this.loadCustomerApplications(value);
      } else {
        this.customerApplications.set([]);
      }
    });
  }

  addLineItem(initial?: { id?: number; customerApplication?: number; amount?: number }): void {
    const group = this.fb.group({
      id: [initial?.id ?? null],
      customerApplication: [initial?.customerApplication ?? null, Validators.required],
      amount: [initial?.amount ?? 0, [Validators.required, Validators.min(0)]],
    });

    group.get('customerApplication')?.valueChanges.subscribe((value) => {
      if (!value) {
        return;
      }
      const app = this.customerApplications().find((item) => item.id === value);
      const price = app?.product?.basePrice ? Number(app.product.basePrice) : 0;
      group.get('amount')?.setValue(Number.isNaN(price) ? 0 : price, { emitEvent: false });
    });

    this.invoiceApplications.push(group);
  }

  removeLineItem(index: number): void {
    if (this.invoiceApplications.length <= 1) {
      return;
    }
    this.invoiceApplications.removeAt(index);
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
        customerApplication: item.customerApplication,
        amount: String(item.amount ?? 0),
      })),
    } as InvoiceCreateUpdate;

    if (this.isEditMode() && this.invoice()) {
      this.invoicesApi.invoicesUpdate(this.invoice()!.id, payload).subscribe({
        next: (invoice: InvoiceCreateUpdate) => {
          this.toast.success('Invoice updated');
          this.router.navigate(['/invoices', invoice.id]);
        },
        error: () => {
          this.toast.error('Failed to update invoice');
          this.isSaving.set(false);
        },
      });
      return;
    }

    this.invoicesApi.invoicesCreate(payload).subscribe({
      next: (invoice: InvoiceCreateUpdate) => {
        this.toast.success('Invoice created');
        this.router.navigate(['/invoices', invoice.id]);
      },
      error: () => {
        this.toast.error('Failed to create invoice');
        this.isSaving.set(false);
      },
    });
  }

  formatCurrency(value: number | null | undefined): string {
    if (value === null || value === undefined) return '—';
    return new Intl.NumberFormat('id-ID', {
      style: 'currency',
      currency: 'IDR',
      maximumFractionDigits: 0,
    }).format(value);
  }

  availableApplications(selectedId?: number | null): DocApplicationInvoice[] {
    const selected = new Set(
      this.invoiceApplications.controls
        .map((group) => group.get('customerApplication')?.value)
        .filter((value) => value !== null && value !== undefined),
    );

    return this.customerApplications().filter(
      (item) => !selected.has(item.id) || item.id === selectedId,
    );
  }

  private loadFromApplication(applicationId: number): void {
    this.isLoading.set(true);
    this.applicationsApi.customerApplicationsRetrieve(applicationId).subscribe({
      next: (app) => {
        const customerId = app.customer?.id;
        if (customerId) {
          this.form.get('customer')?.setValue(customerId, { emitEvent: false });
          this.form.get('customer')?.disable();

          this.invoicesApi
            .invoicesGetCustomerApplicationsList(customerId, undefined, true, undefined, true)
            .subscribe({
              next: (response: PaginatedDocApplicationInvoiceList) => {
                this.customerApplications.set(response.results ?? []);

                this.invoiceApplications.clear();
                const amount = app.product?.basePrice ? Number(app.product.basePrice) : 0;
                this.addLineItem({
                  customerApplication: app.id,
                  amount: Number.isNaN(amount) ? 0 : amount,
                });
                this.isLoading.set(false);
              },
              error: () => {
                this.toast.error('Failed to load billable applications');
                this.isLoading.set(false);
              },
            });
        } else {
          this.isLoading.set(false);
          this.addLineItem();
        }
      },
      error: () => {
        this.toast.error('Failed to load application');
        this.isLoading.set(false);
        this.addLineItem();
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

        this.form.get('customer')?.disable();
        this.form.get('invoiceNo')?.disable();

        this.invoiceApplications.clear();
        (invoice.invoiceApplications ?? []).forEach((item) => {
          this.addLineItem({
            id: item.id,
            customerApplication: item.customerApplication?.id,
            amount: Number(item.amount ?? 0),
          });
        });

        if ((invoice.invoiceApplications ?? []).length === 0) {
          this.addLineItem();
        }

        if (invoice.customer?.id) {
          this.loadCustomerApplications(invoice.customer.id, invoice.id);
        }

        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load invoice');
        this.isLoading.set(false);
      },
    });
  }

  private loadCustomerApplications(customerId: number, currentInvoiceId?: number): void {
    this.invoicesApi
      .invoicesGetCustomerApplicationsList(customerId, currentInvoiceId, true, undefined, true)
      .subscribe({
        next: (response: PaginatedDocApplicationInvoiceList) => {
          this.customerApplications.set(response.results ?? []);
        },
        error: () => {
          this.toast.error('Failed to load customer applications');
        },
      });
  }

  private toIsoDate(value: Date | string | null): string | null {
    if (!value) return null;
    const date = value instanceof Date ? value : new Date(value);
    if (Number.isNaN(date.getTime())) return null;
    return date.toISOString().split('T')[0];
  }

  private proposeInvoiceNo(invoiceDate?: Date | string | null): void {
    if (!invoiceDate) return;
    const date = invoiceDate instanceof Date ? invoiceDate : new Date(invoiceDate);
    if (Number.isNaN(date.getTime())) return;

    // Use local date to avoid timezone shift issues with toISOString()
    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    const dateStr = `${year}-${month}-${day}`;

    const params: any = { invoice_date: dateStr };

    this.http.get<any>(`/api/invoices/propose/`, { params }).subscribe({
      next: (res) => {
        const ctrl = this.form.get('invoiceNo');
        if (ctrl && !ctrl.dirty) {
          // The backend uses djangorestframework-camel-case, so invoice_no becomes invoiceNo
          const proposedNo = res.invoiceNo || res.invoice_no;
          if (proposedNo) {
            ctrl.setValue(proposedNo, { emitEvent: false });
            // mark pristine so future proposals still overwrite unless user edits
            ctrl.markAsPristine();
            this.cdr.markForCheck();
          }
        }
      },
      error: () => {
        // non-fatal — proposal failed, leave invoiceNo empty
      },
    });
  }
}
