import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  HostListener,
  OnInit,
  computed,
  inject,
  signal,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  CustomersService,
  type CountryCode,
  type CustomerDetail,
} from '@/core/services/customers.service';
import { OcrService, type OcrStatusResponse } from '@/core/services/ocr.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-customer-form',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardComboboxComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ZardDateInputComponent,
    FileUploadComponent,
    ZardIconComponent,
    FormErrorSummaryComponent,
    ZardCheckboxComponent,
  ],
  templateUrl: './customer-form.component.html',
  styleUrls: ['./customer-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerFormComponent implements OnInit {
  private fb = inject(FormBuilder);
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private customersService = inject(CustomersService);
  private ocrService = inject(OcrService);
  private toast = inject(GlobalToastService);
  private destroyRef = inject(DestroyRef);

  readonly isLoading = signal(false);
  readonly isEditMode = signal(false);
  readonly customer = signal<CustomerDetail | null>(null);
  readonly countries = signal<CountryCode[]>([]);
  readonly isPerson = signal(true); // Track if customer type is 'person'

  readonly submitted = signal(false);
  readonly passportFile = signal<File | null>(null);
  readonly passportPreviewUrl = signal<string | null>(null);
  readonly passportPastePreviewUrl = signal<string | null>(null);
  readonly passportPasteStatus = signal<string | null>(null);
  readonly ocrUseAi = signal(true);
  readonly ocrProcessing = signal(false);
  readonly ocrMessage = signal<string | null>(null);
  readonly ocrMessageTone = signal<'success' | 'warning' | 'error' | 'info' | null>(null);
  readonly ocrData = signal<OcrStatusResponse | null>(null);
  readonly passportMetadata = signal<Record<string, unknown> | null>(null);

  @HostListener('window:keydown', ['$event'])
  handleGlobalKeydown(event: KeyboardEvent): void {
    // Esc --> Cancel
    if (event.key === 'Escape') {
      event.preventDefault();
      this.onCancel();
      return;
    }

    // cmd+s (mac) or ctrl+s (windows/linux) --> save
    const isSaveKey = (event.ctrlKey || event.metaKey) && (event.key === 's' || event.key === 'S');
    if (isSaveKey) {
      event.preventDefault();
      this.onSubmit();
      return;
    }

    // Only trigger B/Left Arrow if no input is focused (to avoid interference with typing)
    const activeElement = document.activeElement;
    const isInput =
      activeElement instanceof HTMLInputElement ||
      activeElement instanceof HTMLTextAreaElement ||
      (activeElement instanceof HTMLElement && activeElement.isContentEditable);

    if (isInput) return;

    // B or Left Arrow --> Back to list
    if (
      (event.key === 'B' || event.key === 'ArrowLeft') &&
      !event.ctrlKey &&
      !event.altKey &&
      !event.metaKey
    ) {
      event.preventDefault();
      this.onCancel();
    }
  }

  private ocrPollTimer: number | null = null;

  form = this.fb.group(
    {
      customer_type: ['person'],
      title: [''],
      first_name: ['', [Validators.pattern('^([A-Z][a-zA-Z\\s\\-]*)$')]],
      last_name: [''],
      company_name: [''],
      gender: [''],
      nationality: [''],
      birthdate: [null as Date | null],
      birth_place: [''],
      passport_number: [''],
      passport_issue_date: [null as Date | null],
      passport_expiration_date: [null as Date | null],
      npwp: [''],
      email: ['', Validators.email],
      telephone: [''],
      whatsapp: [''],
      telegram: [''],
      facebook: [''],
      instagram: [''],
      twitter: [''],
      address_bali: [''],
      address_abroad: [''],
      notify_documents_expiration: [false],
      notify_by: [''],
      active: [true],
    },
    {
      validators: [
        this.passportDatesValidator.bind(this),
        this.birthDateValidator.bind(this),
        this.notificationValidator.bind(this),
      ],
    },
  );

  readonly formErrorLabels: Record<string, string> = {
    customer_type: 'Customer Type',
    title: 'Title',
    first_name: 'First Name',
    last_name: 'Last Name',
    company_name: 'Company Name',
    gender: 'Gender',
    nationality: 'Nationality',
    birthdate: 'Birthdate',
    birth_place: 'Birth Place',
    passport_number: 'Passport Number',
    passport_issue_date: 'Passport Issue Date',
    passport_expiration_date: 'Passport Expiration Date',
    npwp: 'NPWP',
    email: 'Email',
    telephone: 'Telephone',
    whatsapp: 'WhatsApp',
    telegram: 'Telegram',
    facebook: 'Facebook',
    instagram: 'Instagram',
    twitter: 'Twitter',
    address_bali: 'Address (Bali)',
    address_abroad: 'Address (Abroad)',
    notify_documents_expiration: 'Notify Documents Expiration',
    notify_by: 'Notify By',
    active: 'Active',
  };

  // Title options
  readonly titleOptions = [
    { value: '', label: '---------' },
    { value: 'Mr', label: 'Mr' },
    { value: 'Mrs', label: 'Mrs' },
    { value: 'Ms', label: 'Ms' },
    { value: 'Miss', label: 'Miss' },
    { value: 'Dr', label: 'Dr' },
    { value: 'Prof', label: 'Prof' },
  ];

  // Gender options
  readonly genderOptions = [
    { value: '', label: '---------' },
    { value: 'M', label: 'Male' },
    { value: 'F', label: 'Female' },
  ];

  // Notify by options
  readonly notifyByOptions = [
    { value: '', label: '---------' },
    { value: 'Email', label: 'Email' },
    { value: 'SMS', label: 'SMS' },
    { value: 'WhatsApp', label: 'WhatsApp' },
    { value: 'Telegram', label: 'Telegram' },
    { value: 'Telephone', label: 'Telephone' },
  ];

  // Nationality options (for z-combobox)
  readonly nationalityOptions = computed<ZardComboboxOption[]>(() => {
    const list = this.countries() ?? [];
    const opts: ZardComboboxOption[] = [{ value: '', label: '---------' }];
    for (const c of list) {
      opts.push({ value: c.alpha3Code, label: `${c.country} (${c.alpha3Code})` });
    }
    return opts;
  });

  ngOnInit(): void {
    // Load countries for the nationality dropdown
    this.customersService.getCountries().subscribe({
      next: (data) => this.countries.set(data),
      error: () => this.toast.error('Failed to load countries'),
    });

    // Re-run group validators when related fields change.
    this.form.get('passport_issue_date')?.valueChanges.subscribe(() => {
      this.form.updateValueAndValidity({ onlySelf: false, emitEvent: false });
    });
    this.form.get('passport_expiration_date')?.valueChanges.subscribe(() => {
      this.form.updateValueAndValidity({ onlySelf: false, emitEvent: false });
    });
    this.form.get('birthdate')?.valueChanges.subscribe(() => {
      this.form.updateValueAndValidity({ onlySelf: false, emitEvent: false });
    });
    this.form.get('notify_documents_expiration')?.valueChanges.subscribe(() => {
      this.form.updateValueAndValidity({ onlySelf: false, emitEvent: false });
    });
    this.form.get('notify_by')?.valueChanges.subscribe(() => {
      this.form.updateValueAndValidity({ onlySelf: false, emitEvent: false });
    });

    // Set up conditional validation based on customer_type changes
    this.form.get('customer_type')?.valueChanges.subscribe((customerType) => {
      this.updateConditionalValidators(customerType ?? 'person');
    });

    // Initial validation setup
    this.updateConditionalValidators(this.form.get('customer_type')?.value ?? 'person');

    // Load customer data if in edit mode
    const idParam = this.route.snapshot.paramMap.get('id');
    if (idParam) {
      this.isEditMode.set(true);
      const id = Number(idParam);
      this.isLoading.set(true);
      this.customersService.getCustomer(id).subscribe({
        next: (data) => {
          this.customer.set(data);
          // Update isPerson immediately based on loaded data
          this.isPerson.set(data.customerType === 'person');
          this.form.patchValue({
            customer_type: data.customerType ?? 'person',
            title: data.title ?? '',
            first_name: data.firstName ?? '',
            last_name: data.lastName ?? '',
            company_name: data.companyName ?? '',
            gender: data.gender ?? '',
            nationality: data.nationality ?? '',
            birthdate: data.birthdate ? new Date(data.birthdate) : null,
            birth_place: data.birthPlace ?? '',
            passport_number: data.passportNumber ?? '',
            passport_issue_date: data.passportIssueDate ? new Date(data.passportIssueDate) : null,
            passport_expiration_date: data.passportExpirationDate
              ? new Date(data.passportExpirationDate)
              : null,
            npwp: data.npwp ?? '',
            email: data.email ?? '',
            telephone: data.telephone ?? '',
            whatsapp: data.whatsapp ?? '',
            telegram: data.telegram ?? '',
            facebook: data.facebook ?? '',
            instagram: data.instagram ?? '',
            twitter: data.twitter ?? '',
            address_bali: data.addressBali ?? '',
            address_abroad: data.addressAbroad ?? '',
            notify_documents_expiration: data.notifyDocumentsExpiration ?? false,
            notify_by: data.notifyBy ?? '',
            active: data.active ?? true,
          });
          this.isLoading.set(false);
        },
        error: () => {
          this.toast.error('Failed to load customer');
          this.isLoading.set(false);
        },
      });
    }

    this.destroyRef.onDestroy(() => {
      if (this.ocrPollTimer) {
        window.clearTimeout(this.ocrPollTimer);
      }
    });
  }

  onPassportFileSelected(file: File): void {
    this.passportFile.set(file);
    this.passportPreviewUrl.set(null);
    this.ocrMessage.set(null);
    this.ocrMessageTone.set(null);
  }

  onPassportFileCleared(): void {
    this.passportFile.set(null);
    this.passportPreviewUrl.set(null);
    this.ocrMessage.set(null);
    this.ocrMessageTone.set(null);
  }

  onPastePassport(event: ClipboardEvent): void {
    if (!this.isPerson()) {
      this.toast.error('Passport import is only available for person customers');
      event.preventDefault();
      return;
    }

    const items = event.clipboardData?.items;
    if (!items) {
      return;
    }

    for (const item of Array.from(items)) {
      if (item.type?.includes('image')) {
        const file = item.getAsFile();
        if (!file) {
          continue;
        }
        const reader = new FileReader();
        reader.onload = () => {
          this.passportPastePreviewUrl.set(String(reader.result));
        };
        reader.readAsDataURL(file);
        this.passportPasteStatus.set('Uploading...');
        this.passportFile.set(file);
        this.runPassportImport(file);
        event.preventDefault();
        break;
      }
    }
  }

  onToggleUseAi(event: Event): void {
    const target = event.target as HTMLInputElement | null;
    this.ocrUseAi.set(Boolean(target?.checked));
  }

  onPassportImport(): void {
    if (!this.isPerson()) {
      this.toast.error('Passport import is only available for person customers');
      return;
    }
    const file = this.passportFile();
    if (!file) {
      this.ocrMessage.set('No file selected');
      this.ocrMessageTone.set('error');
      return;
    }
    this.runPassportImport(file);
  }

  private runPassportImport(file: File): void {
    this.ocrProcessing.set(true);
    this.ocrMessage.set(this.ocrUseAi() ? 'Processing with AI...' : 'Processing...');
    this.ocrMessageTone.set('info');

    this.ocrService
      .startPassportOcr(file, {
        useAi: this.ocrUseAi(),
        saveSession: true,
        previewWidth: 500,
      })
      .subscribe({
        next: (response) => {
          const statusUrl =
            ('statusUrl' in response && response.statusUrl) ||
            (response as { status_url?: string }).status_url;
          if (statusUrl) {
            this.pollOcrStatus(statusUrl, 0);
            return;
          }
          this.handleOcrResult(response as OcrStatusResponse);
        },
        error: (error) => {
          this.ocrProcessing.set(false);
          this.ocrMessage.set(this.extractOcrError(error) ?? 'Upload failed');
          this.ocrMessageTone.set('error');
        },
      });
  }

  private pollOcrStatus(statusUrl: string, attempt: number): void {
    const maxAttempts = 90;
    const intervalMs = 2000;

    if (attempt >= maxAttempts) {
      this.ocrProcessing.set(false);
      this.ocrMessage.set('OCR processing timed out');
      this.ocrMessageTone.set('error');
      return;
    }

    this.ocrPollTimer = window.setTimeout(() => {
      this.ocrService.getOcrStatus(statusUrl).subscribe({
        next: (status) => {
          if (status.status === 'completed') {
            this.handleOcrResult(status);
            return;
          }
          if (status.status === 'failed') {
            this.ocrProcessing.set(false);
            this.ocrMessage.set(status.error ?? 'OCR failed');
            this.ocrMessageTone.set('error');
            return;
          }
          if (typeof status.progress === 'number') {
            this.ocrMessage.set(`Processing... ${status.progress}%`);
          } else {
            this.ocrMessage.set('Processing...');
          }
          this.ocrMessageTone.set('info');
          this.pollOcrStatus(statusUrl, attempt + 1);
        },
        error: (error) => {
          this.ocrProcessing.set(false);
          this.ocrMessage.set(this.extractOcrError(error) ?? 'OCR status check failed');
          this.ocrMessageTone.set('error');
        },
      });
    }, intervalMs);
  }

  private handleOcrResult(status: OcrStatusResponse): void {
    this.ocrProcessing.set(false);
    this.ocrData.set(status);

    const mrz = (status.mrzData ??
      (status as { mrz_data?: OcrStatusResponse['mrzData'] }).mrz_data) as
      | NonNullable<OcrStatusResponse['mrzData']>
      | undefined;
    if (!mrz) {
      this.ocrMessage.set('OCR completed but no data was extracted');
      this.ocrMessageTone.set('error');
      return;
    }

    const confidence =
      this.getMrzValue<number>(mrz, 'aiConfidenceScore', 'ai_confidence_score') ?? null;
    const aiWarning = (status.aiWarning ?? (status as { ai_warning?: string }).ai_warning) || null;
    const hasMismatches =
      this.getMrzValue<boolean>(mrz, 'hasMismatches', 'has_mismatches') ?? false;
    const mismatchSummary =
      this.getMrzValue<string>(mrz, 'mismatchSummary', 'mismatch_summary') ??
      'Field mismatches detected.';
    const extractionMethod = this.getMrzValue<string>(mrz, 'extractionMethod', 'extraction_method');

    if (aiWarning) {
      this.ocrMessage.set(`OCR completed with warning: ${aiWarning}`);
      this.ocrMessageTone.set('warning');
    } else if (hasMismatches) {
      this.ocrMessage.set(
        `Data imported with warnings. ${mismatchSummary}` +
          (confidence !== null ? ` (confidence ${(confidence * 100).toFixed(0)}%)` : ''),
      );
      this.ocrMessageTone.set('warning');
    } else if (extractionMethod === 'ai_only' && confidence !== null) {
      this.ocrMessage.set(
        `Data imported via AI (Passport OCR failed, confidence ${(confidence * 100).toFixed(0)}%)`,
      );
      this.ocrMessageTone.set('success');
    } else if (extractionMethod === 'hybridMrzAi' && confidence !== null) {
      this.ocrMessage.set(
        `Data imported via OCR + AI (confidence ${(confidence * 100).toFixed(0)}%)`,
      );
      this.ocrMessageTone.set('success');
    } else {
      this.ocrMessage.set('Data successfully imported via OCR');
      this.ocrMessageTone.set('success');
    }

    const previewImage =
      status.b64ResizedImage ?? (status as { b64_resized_image?: string }).b64_resized_image;
    if (previewImage) {
      this.passportPreviewUrl.set(`data:image/jpeg;base64,${previewImage}`);
    }

    this.passportMetadata.set(mrz as unknown as Record<string, unknown>);
    this.patchFormFromMrz(mrz);
    this.passportPasteStatus.set(null);
  }

  private patchFormFromMrz(mrz: NonNullable<OcrStatusResponse['mrzData']>): void {
    const titleValue = mrz.sex === 'M' ? 'Mr' : mrz.sex === 'F' ? 'Ms' : '';

    this.form.patchValue({
      first_name: this.getMrzValue(mrz, 'names') ?? this.form.get('first_name')?.value,
      last_name: this.getMrzValue(mrz, 'surname') ?? this.form.get('last_name')?.value,
      gender: this.getMrzValue(mrz, 'sex') ?? this.form.get('gender')?.value,
      title: titleValue || this.form.get('title')?.value,
      nationality: this.getMrzValue(mrz, 'nationality') ?? this.form.get('nationality')?.value,
      birthdate:
        this.parseDate(this.getMrzValue(mrz, 'dateOfBirthYyyyMmDd', 'date_of_birth_yyyy_mm_dd')) ??
        this.form.get('birthdate')?.value,
      birth_place:
        this.getMrzValue(mrz, 'birthPlace', 'birth_place') ?? this.form.get('birth_place')?.value,
      passport_number: this.getMrzValue(mrz, 'number') ?? this.form.get('passport_number')?.value,
      passport_issue_date:
        this.parseDate(
          this.getMrzValue(mrz, 'passportIssueDate', 'passport_issue_date') ??
            this.getMrzValue(mrz, 'issueDateYyyyMmDd', 'issue_date_yyyy_mm_dd'),
        ) ?? this.form.get('passport_issue_date')?.value,
      passport_expiration_date:
        this.parseDate(
          this.getMrzValue(mrz, 'expirationDateYyyyMmDd', 'expiration_date_yyyy_mm_dd'),
        ) ?? this.form.get('passport_expiration_date')?.value,
      address_abroad:
        this.getMrzValue(mrz, 'addressAbroad', 'address_abroad') ??
        this.form.get('address_abroad')?.value,
    });
  }

  private getMrzValue<T = string>(
    mrz: NonNullable<OcrStatusResponse['mrzData']>,
    camelKey: string,
    snakeKey?: string,
  ): T | undefined {
    const record = mrz as Record<string, unknown>;
    if (record[camelKey] !== undefined) {
      return record[camelKey] as T;
    }
    if (snakeKey && record[snakeKey] !== undefined) {
      return record[snakeKey] as T;
    }
    return undefined;
  }

  private parseDate(value?: string | null): Date | null {
    if (!value) {
      return null;
    }
    const parsed = new Date(value);
    return Number.isNaN(parsed.getTime()) ? null : parsed;
  }

  private extractOcrError(error: unknown): string | null {
    if (!error || typeof error !== 'object') {
      return null;
    }
    const message = (error as { message?: string }).message;
    if (message) {
      return message;
    }
    const errorMessage = (error as { error?: string }).error;
    return errorMessage ?? null;
  }

  private passportDatesValidator(
    group: import('@angular/forms').AbstractControl,
  ): import('@angular/forms').ValidationErrors | null {
    const issue = group.get('passport_issue_date')?.value as Date | null;
    const expiration = group.get('passport_expiration_date')?.value as Date | null;

    // Clear related errors first
    group.get('passport_expiration_date')?.setErrors(null);

    if (issue && expiration) {
      if (expiration < issue) {
        group.get('passport_expiration_date')?.setErrors({ passportExpirationBeforeIssue: true });
        return { passportExpirationBeforeIssue: true };
      }
    }
    return null;
  }

  private birthDateValidator(
    group: import('@angular/forms').AbstractControl,
  ): import('@angular/forms').ValidationErrors | null {
    const birth = group.get('birthdate')?.value as Date | null;
    const issue = group.get('passport_issue_date')?.value as Date | null;
    const expiration = group.get('passport_expiration_date')?.value as Date | null;

    // Clear existing birth errors
    group.get('birthdate')?.setErrors(null);

    if (!birth) return null;

    if (issue && birth > issue) {
      group.get('birthdate')?.setErrors({ birthdateAfterIssue: true });
      return { birthdateAfterIssue: true };
    }

    if (expiration && birth > expiration) {
      group.get('birthdate')?.setErrors({ birthdateAfterExpiration: true });
      return { birthdateAfterExpiration: true };
    }

    return null;
  }

  private notificationValidator(
    group: import('@angular/forms').AbstractControl,
  ): import('@angular/forms').ValidationErrors | null {
    const notify = group.get('notify_documents_expiration')?.value;
    const notifyBy = group.get('notify_by')?.value;

    const notifyByControl = group.get('notify_by');
    if (notify && !notifyBy) {
      notifyByControl?.setErrors({ ...notifyByControl.errors, notifyByRequired: true });
      return { notifyByRequired: true };
    }

    // Only clear error if it was set by this validator
    if (notifyByControl?.hasError('notifyByRequired')) {
      const errors = { ...notifyByControl.errors };
      delete errors['notifyByRequired'];
      notifyByControl.setErrors(Object.keys(errors).length ? errors : null);
    }

    return null;
  }

  private updateConditionalValidators(customerType: string): void {
    // Update isPerson signal
    this.isPerson.set(customerType === 'person');

    const firstNameControl = this.form.get('first_name');
    const lastNameControl = this.form.get('last_name');
    const companyNameControl = this.form.get('company_name');

    if (customerType === 'person') {
      firstNameControl?.setValidators([
        Validators.required,
        Validators.pattern('^([A-Z][a-zA-Z\\s\\-]*)$'),
      ]);
      lastNameControl?.setValidators([Validators.required]);
      companyNameControl?.clearValidators();
    } else if (customerType === 'company') {
      firstNameControl?.clearValidators();
      firstNameControl?.setValidators([Validators.pattern('^([A-Z][a-zA-Z\\s\\-]*)$')]);
      lastNameControl?.clearValidators();
      companyNameControl?.setValidators([Validators.required]);
    }

    firstNameControl?.updateValueAndValidity({ emitEvent: false });
    lastNameControl?.updateValueAndValidity({ emitEvent: false });
    companyNameControl?.updateValueAndValidity({ emitEvent: false });
  }

  formatName(controlName: 'first_name' | 'last_name'): void {
    const control = this.form.get(controlName);
    const value = control?.value;
    if (value && typeof value === 'string' && value.trim().length > 0) {
      const trimmed = value.trim();
      const formatted = trimmed.charAt(0).toUpperCase() + trimmed.slice(1);
      if (formatted !== value) {
        control.setValue(formatted, { emitEvent: false });
        control.updateValueAndValidity();
      }
    }
  }

  onCancel(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    const st = (history.state as any) || {};
    const state: Record<string, unknown> = { focusTable: true };
    if (idParam) {
      const id = Number(idParam);
      if (id) state['focusId'] = id;
    }
    if (st.searchQuery) state['searchQuery'] = st.searchQuery;
    this.router.navigate(['/customers'], { state });
  }

  onSubmit(): void {
    this.submitted.set(true);

    if (this.form.invalid) {
      this.toast.error('Please fix validation errors');
      return;
    }

    const rawValue = this.form.getRawValue();

    // Use a helper to format dates consistently in local time (YYYY-MM-DD)
    const formatDate = (date: Date | null) => {
      if (!date || isNaN(date.getTime())) return null;
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    };

    // Construct payload with camelCase keys expected by the API
    const payload = {
      ...rawValue,
      customerType: rawValue.customer_type,
      firstName: rawValue.first_name,
      lastName: rawValue.last_name,
      companyName: rawValue.company_name,
      addressBali: rawValue.address_bali,
      addressAbroad: rawValue.address_abroad,
      birthdate: formatDate(rawValue.birthdate),
      passportNumber: rawValue.passport_number,
      passportIssueDate: formatDate(rawValue.passport_issue_date),
      passportExpirationDate: formatDate(rawValue.passport_expiration_date),
      birthPlace: rawValue.birth_place,
      notifyDocumentsExpiration: rawValue.notify_documents_expiration,
      notifyBy: rawValue.notify_by,
      passportMetadata: this.passportMetadata(),
    };
    this.isLoading.set(true);

    const file = this.passportFile();
    const requestPayload = file ? this.buildFormData(payload, file) : payload;

    if (this.isEditMode()) {
      const id = Number(this.route.snapshot.paramMap.get('id'));
      this.customersService.updateCustomer(id, requestPayload).subscribe({
        next: (data) => {
          this.toast.success('Customer updated');
          this.router.navigate(['/customers', data.id]);
        },
        error: (error) => {
          applyServerErrorsToForm(this.form, error);
          this.form.markAllAsTouched();
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to update customer: ${message}` : 'Failed to update customer',
          );
          this.isLoading.set(false);
        },
      });
    } else {
      this.customersService.createCustomer(requestPayload).subscribe({
        next: (data) => {
          this.toast.success('Customer created');
          this.router.navigate(['/customers', data.id]);
        },
        error: (error) => {
          applyServerErrorsToForm(this.form, error);
          this.form.markAllAsTouched();
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to create customer: ${message}` : 'Failed to create customer',
          );
          this.isLoading.set(false);
        },
      });
    }
  }

  private buildFormData(payload: Record<string, unknown>, file: File): FormData {
    const formData = new FormData();
    Object.entries(payload).forEach(([key, value]) => {
      if (value === undefined || value === null || value === '') {
        return;
      }
      if (typeof value === 'object') {
        formData.append(key, JSON.stringify(value));
      } else {
        formData.append(key, String(value));
      }
    });
    formData.append('passport_file', file);
    return formData;
  }
}
