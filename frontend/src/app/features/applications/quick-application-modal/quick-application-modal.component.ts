import { CustomerApplicationsService } from '@/core/api';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { ZardDialogService } from '@/shared/components/dialog';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardInputDirective } from '@/shared/components/input';
import { ProductSelectComponent } from '@/shared/components/product-select';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';
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
import { catchError, of, switchMap } from 'rxjs';

@Component({
  selector: 'app-quick-application-modal',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardButtonComponent,
    ZardInputDirective,
    ZardDateInputComponent,
    ProductSelectComponent,
    FormErrorSummaryComponent,
  ],
  templateUrl: './quick-application-modal.component.html',
  styleUrls: ['./quick-application-modal.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class QuickApplicationModalComponent {
  private dialogService = inject(ZardDialogService);
  private destroyRef = inject(DestroyRef);
  private fb = inject(FormBuilder);
  private applicationsApi = inject(CustomerApplicationsService);
  private toast = inject(GlobalToastService);

  readonly isOpen = input<boolean>(false);
  readonly customerId = input<number | null | undefined>(null);

  readonly saved = output<any>();
  readonly closed = output<void>();

  private dialogRef = signal<ReturnType<ZardDialogService['create']> | null>(null);

  readonly contentTemplate = viewChild.required<TemplateRef<unknown>>('contentTemplate');

  readonly isSaving = signal(false);

  readonly form = this.fb.group({
    product: [null as string | null, Validators.required],
    docDate: [new Date(), Validators.required],
    notes: [''],
  });

  readonly formErrorLabels: Record<string, string> = {
    product: 'Product',
    docDate: 'Document Date',
    notes: 'Notes',
  };

  constructor() {
    effect(() => {
      const open = this.isOpen();
      const current = this.dialogRef();

      if (open && !current) {
        this.resetForm();
        const ref = this.dialogService.create({
          zTitle: 'Quick Add Application',
          zContent: this.contentTemplate(),
          zHideFooter: true,
          zClosable: true,
          zWidth: '1200px',
          zCustomClasses: 'max-w-[1200px] sm:max-w-[1200px]',
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

  private resetForm(): void {
    this.form.reset({
      product: null,
      docDate: new Date(),
      notes: '',
    });
  }

  submit(): void {
    if (this.form.invalid || !this.customerId()) {
      this.form.markAllAsTouched();
      return;
    }

    this.isSaving.set(true);

    const raw = this.form.getRawValue();
    const docDateStr =
      raw.docDate instanceof Date ? raw.docDate.toISOString().split('T')[0] : raw.docDate;

    const payload = {
      customer: this.customerId()!,
      product: Number(raw.product),
      docDate: docDateStr,
      notes: raw.notes ?? '',
      documentTypes: [], // No documents for quick add
    };

    // 1. Create Application
    // 2. Force Close it
    // 3. Emit saved event
    this.applicationsApi
      .customerApplicationsCreate(payload as any)
      .pipe(
        switchMap((newApp: any) => {
          return this.applicationsApi.customerApplicationsRetrieve(newApp.id).pipe(
            switchMap((detail: any) => {
              const status = String(detail?.status ?? '').toLowerCase();
              const canForceClose = detail?.canForceClose !== false;
              if (status === 'completed' || !canForceClose) {
                return of(detail);
              }

              // Prepare a minimal payload for force-close that matches the expected serializer
              const forceClosePayload = {
                ...detail,
                customer: detail.customer?.id ?? detail.customer,
                product: detail.product?.id ?? detail.product,
              };

              return this.applicationsApi
                .customerApplicationsForceCloseCreate(detail.id, forceClosePayload)
                .pipe(
                  catchError((error) => {
                    const message = extractServerErrorMessage(error)?.toLowerCase() ?? '';
                    if (message.includes('already completed')) {
                      return of(detail);
                    }
                    throw error;
                  }),
                );
            }),
            catchError(() => of(newApp)),
          );
        }),
      )
      .subscribe({
        next: (finalApp: any) => {
          this.toast.success('Application created and force-closed');
          this.saved.emit(finalApp);
          this.isSaving.set(false);
          this.close();
        },
        error: (error) => {
          applyServerErrorsToForm(this.form, error);
          this.form.markAllAsTouched();
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to create application: ${message}` : 'Failed to create application',
          );
          this.isSaving.set(false);
        },
      });
  }

  close(): void {
    this.closed.emit();
  }
}
