import { CommonModule } from '@angular/common';
import { HttpResponse } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators, type FormGroup } from '@angular/forms';
import { ActivatedRoute, Router } from '@angular/router';
import { Observable, Subscription } from 'rxjs';

import {
  CustomersService,
  type CountryCode,
  type CustomerDetail,
} from '@/core/services/customers.service';
import { OcrService, type OcrStatusResponse } from '@/core/services/ocr.service';
import { JobService } from '@/core/services/job.service';
import { SseService } from '@/core/services/sse.service';
import { BaseFormComponent, BaseFormConfig } from '@/shared/core/base-form.component';
import { AsyncJob } from '@/core/api';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardCheckboxComponent } from '@/shared/components/checkbox';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { FormErrorSummaryComponent } from '@/shared/components/form-error-summary/form-error-summary.component';
import { ZardIconComponent } from '@/shared/components/icon';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import { ZardInputDirective } from '@/shared/components/input';
import {
  buildExistingDocumentPreview,
  buildLocalFilePreview,
} from '@/shared/utils/document-preview-source';
import { applyServerErrorsToForm, extractServerErrorMessage } from '@/shared/utils/form-errors';

// Type definitions for DTOs
interface CustomerCreateDto {
  [key: string]: unknown;
  customerType: string;
  firstName?: string;
  lastName?: string;
  companyName?: string;
  gender?: string;
  nationality?: string;
  birthdate?: string | null;
  birthPlace?: string;
  passportNumber?: string;
  passportIssueDate?: string | null;
  passportExpirationDate?: string | null;
  npwp?: string;
  email?: string;
  telephone?: string;
  whatsapp?: string;
  telegram?: string;
  facebook?: string;
  instagram?: string;
  twitter?: string;
  addressBali?: string;
  addressAbroad?: string;
  notifyDocumentsExpiration?: boolean;
  notifyBy?: string;
  active?: boolean;
  title?: string;
  passportMetadata?: Record<string, unknown> | null;
}

interface CustomerUpdateDto extends CustomerCreateDto {
  id?: number;
}

/**
 * Customer form component
 * 
 * Extends BaseFormComponent to inherit common form patterns:
 * - Keyboard shortcuts (Ctrl/Cmd+S to save, Escape to cancel)
 * - Edit mode detection from route
 * - Server error handling
 * - Loading states
 * 
 * Note: This component has extensive OCR functionality that is component-specific
 */
@Component({
  selector: 'app-customer-form',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardInputDirective,
    ZardComboboxComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ZardDateInputComponent,
    FileUploadComponent,
    ZardIconComponent,
    ImageMagnifierComponent,
    FormErrorSummaryComponent,
    ZardCheckboxComponent,
  ],
  templateUrl: './customer-form.component.html',
  styleUrls: ['./customer-form.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CustomerFormComponent extends BaseFormComponent<
  CustomerDetail,
  CustomerCreateDto,
  CustomerUpdateDto
> implements OnInit {
  private readonly customersService = inject(CustomersService);
  private readonly ocrService = inject(OcrService);
  private readonly sseService = inject(SseService);
  private readonly jobService = inject(JobService);

  // Customer-specific state
  readonly countries = signal<CountryCode[]>([]);
  readonly isPerson = signal(true);
  readonly submitted = signal(false);
  readonly passportFile = signal<File | null>(null);
  readonly passportFilePreviewUrl = signal<string | null>(null);
  readonly passportFilePreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPassportPreviewUrl = signal<string | null>(null);
  readonly existingPassportPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPassportFileName = signal<string | null>(null);
  readonly activePassportPreviewUrl = computed(
    () => this.passportFilePreviewUrl() ?? this.existingPassportPreviewUrl(),
  );
  readonly activePassportPreviewType = computed(() =>
    this.passportFilePreviewUrl()
      ? this.passportFilePreviewType()
      : this.existingPassportPreviewType(),
  );
  readonly hasExistingPassportFile = computed(
    () => this.isEditMode() && !!this.customer()?.passportFile && !this.passportFile(),
  );
  readonly passportPreviewUrl = signal<string | null>(null);
  readonly passportPastePreviewUrl = signal<string | null>(null);
  readonly passportPasteStatus = signal<string | null>(null);
  readonly ocrUseAi = signal(true);
  readonly ocrProcessing = signal(false);
  readonly ocrMessage = signal<string | null>(null);
  readonly ocrMessageTone = signal<'success' | 'warning' | 'error' | 'info' | null>(null);
  readonly ocrData = signal<OcrStatusResponse | null>(null);
  readonly passportMetadata = signal<Record<string, unknown> | null>(null);

  // Customer reference for template compatibility
  readonly customer = signal<CustomerDetail | null>(null);

  // OCR tracking
  private pollSub: Subscription | null = null;

  // Form error labels
  override readonly formErrorLabels: Record<string, string> = {
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

  // Nationality options
  readonly nationalityOptions = computed<ZardComboboxOption[]>(() => {
    const list = this.countries() ?? [];
    const opts: ZardComboboxOption[] = [{ value: '', label: '---------' }];
    for (const c of list) {
      opts.push({ value: c.alpha3Code, label: `${c.country} (${c.alpha3Code})` });
    }
    return opts;
  });

  constructor() {
    super();
    this.config = {
      entityType: 'customers',
      entityLabel: 'Customer',
    } as BaseFormConfig<CustomerDetail, CustomerCreateDto, CustomerUpdateDto>;
  }

  /**
   * Build the customer form
   */
  protected override buildForm(): FormGroup {
    return this.fb.group(
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
  }

  /**
   * Load customer for edit mode
   */
  protected override loadItem(id: number): Observable<CustomerDetail> {
    return this.customersService.getCustomer(id);
  }

  /**
   * Create DTO from form value
   */
  protected override createDto(): CustomerCreateDto {
    return this.buildPayload();
  }

  /**
   * Update DTO from form value
   */
  protected override updateDto(): CustomerUpdateDto {
    return this.buildPayload();
  }

  /**
   * Save new customer
   */
  protected override saveCreate(dto: CustomerCreateDto): Observable<any> {
    const file = this.passportFile();
    const requestPayload = file ? this.buildFormData(dto, file) : dto;
    return this.customersService.createCustomer(requestPayload);
  }

  /**
   * Update existing customer
   */
  protected override saveUpdate(dto: CustomerUpdateDto): Observable<any> {
    const file = this.passportFile();
    const requestPayload = file ? this.buildFormData(dto, file) : dto;
    return this.customersService.updateCustomer(this.itemId!, requestPayload as any);
  }

  /**
   * Initialize component
   */
  override ngOnInit(): void {
    // Call base ngOnInit for standard initialization
    super.ngOnInit();

    // Load countries for the nationality dropdown
    this.customersService.getCountries().subscribe({
      next: (data) => this.countries.set(data),
      error: () => this.toast.error('Failed to load countries'),
    });

    // Re-run group validators when related fields change
    this.setupValueChangeSubscriptions();

    // Set up conditional validation based on customer_type changes
    this.form.get('customer_type')?.valueChanges.subscribe((customerType) => {
      this.updateConditionalValidators(customerType ?? 'person');
    });

    // Initial validation setup
    this.updateConditionalValidators(this.form.get('customer_type')?.value ?? 'person');

    // Cleanup on destroy
    this.destroyRef.onDestroy(() => {
      this.clearPassportFilePreview();
      this.clearOcrAsyncTracking();
    });
  }

  /**
   * Patch form with customer data - override to handle date conversion
   */
  protected override patchForm(customer: CustomerDetail): void {
    // Set existing passport preview if available
    this.setExistingPassportPreview(customer.passportFile);
    
    // Update isPerson based on loaded data
    this.isPerson.set(customer.customerType === 'person');
    
    // Helper function to parse date strings to Date objects
    const parseDate = (dateString: string | null | undefined): Date | null => {
      if (!dateString) return null;
      const parsed = new Date(dateString);
      return isNaN(parsed.getTime()) ? null : parsed;
    };

    this.form.patchValue({
      customer_type: customer.customerType ?? 'person',
      title: customer.title ?? '',
      first_name: customer.firstName ?? '',
      last_name: customer.lastName ?? '',
      company_name: customer.companyName ?? '',
      gender: customer.gender ?? '',
      nationality: customer.nationality ?? '',
      birthdate: parseDate(customer.birthdate),
      birth_place: customer.birthPlace ?? '',
      passport_number: customer.passportNumber ?? '',
      passport_issue_date: parseDate(customer.passportIssueDate),
      passport_expiration_date: parseDate(customer.passportExpirationDate),
      npwp: customer.npwp ?? '',
      email: customer.email ?? '',
      telephone: customer.telephone ?? '',
      whatsapp: customer.whatsapp ?? '',
      telegram: customer.telegram ?? '',
      facebook: customer.facebook ?? '',
      instagram: customer.instagram ?? '',
      twitter: customer.twitter ?? '',
      address_bali: customer.addressBali ?? '',
      address_abroad: customer.addressAbroad ?? '',
      notify_documents_expiration: customer.notifyDocumentsExpiration ?? false,
      notify_by: customer.notifyBy ?? '',
      active: customer.active ?? true,
    }, { emitEvent: false });
  }

  /**
   * Handle keyboard shortcuts - extends base class
   */
  override handleGlobalKeydown(event: KeyboardEvent): void {
    // Call base for standard shortcuts
    super.handleGlobalKeydown(event);
  }

  /**
   * Cancel and go back - override to preserve navigation state
   */
  override onCancel(): void {
    const idParam = this.route.snapshot.paramMap.get('id');
    const st = (history.state as any) || {};
    const state: Record<string, unknown> = { focusTable: true };
    if (idParam) {
      const id = Number(idParam);
      if (id) state['focusId'] = id;
    }
    if (st.searchQuery) state['searchQuery'] = st.searchQuery;
    const page = Number(st.page);
    if (Number.isFinite(page) && page > 0) {
      state['page'] = Math.floor(page);
    }
    this.router.navigate(['/customers'], { state });
  }

  /**
   * Handle passport file selection
   */
  onPassportFileSelected(file: File): void {
    this.setPassportFilePreview(file);
    this.passportFile.set(file);
    this.passportPreviewUrl.set(null);
    this.ocrMessage.set(null);
    this.ocrMessageTone.set(null);
  }

  /**
   * Handle passport file clear
   */
  onPassportFileCleared(): void {
    this.clearPassportFilePreview();
    this.passportFile.set(null);
    this.passportPreviewUrl.set(null);
    this.ocrMessage.set(null);
    this.ocrMessageTone.set(null);
  }

  /**
   * Handle paste passport from clipboard
   */
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

  /**
   * Toggle AI usage for OCR
   */
  onToggleUseAi(event: Event): void {
    const target = event.target as HTMLInputElement | null;
    this.ocrUseAi.set(Boolean(target?.checked));
  }

  /**
   * Run passport import
   */
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

  /**
   * Format name field
   */
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

  // Private methods for OCR and form handling
  private setupValueChangeSubscriptions(): void {
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
  }

  private setPassportFilePreview(file: File): void {
    this.clearPassportFilePreview();
    const preview = buildLocalFilePreview(file);
    this.passportFilePreviewType.set(preview.type);
    this.passportFilePreviewUrl.set(preview.url);
  }

  private clearPassportFilePreview(): void {
    const url = this.passportFilePreviewUrl();
    if (url && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch {
        // ignore
      }
    }
    this.passportFilePreviewUrl.set(null);
    this.passportFilePreviewType.set('unknown');
  }

  private setExistingPassportPreview(fileUrl: string | null | undefined): void {
    const normalizedUrl = (fileUrl ?? '').trim();
    if (!normalizedUrl) {
      this.existingPassportPreviewUrl.set(null);
      this.existingPassportPreviewType.set('unknown');
      this.existingPassportFileName.set(null);
      return;
    }

    const preview = buildExistingDocumentPreview({ fileLink: normalizedUrl });
    this.existingPassportPreviewUrl.set(preview.url);
    this.existingPassportPreviewType.set(preview.type);
    this.existingPassportFileName.set(this.extractFilenameFromUrl(normalizedUrl));
  }

  private extractFilenameFromUrl(fileUrl: string): string {
    try {
      const pathname = new URL(fileUrl).pathname;
      const filename = pathname.split('/').pop() ?? '';
      return decodeURIComponent(filename) || 'passport-file';
    } catch {
      const withoutQuery = fileUrl.split('?')[0]?.split('#')[0] ?? '';
      const filename = withoutQuery.split('/').pop() ?? '';
      return decodeURIComponent(filename) || 'passport-file';
    }
  }

  private runPassportImport(file: File): void {
    this.clearOcrAsyncTracking();
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
          const jobId =
            ('jobId' in response && response.jobId) ||
            (response as { job_id?: string }).job_id;
          
          if (jobId && typeof jobId === 'string') {
            this.subscribeToOcrStream(jobId);
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

  private subscribeToOcrStream(jobId: string): void {
    this.clearOcrAsyncTracking();

    this.pollSub = this.jobService.watchJob(jobId).subscribe({
      next: (jobStatus: AsyncJob) => {
        if (jobStatus.status === 'completed') {
          // Job is complete, get the final result mapping it as OcrStatusResponse
          const jobResult = (jobStatus.result as Record<string, any>) || {};
          const result: OcrStatusResponse = {
            ...jobResult,
            status: 'completed',
            jobId: jobStatus.id,
          };
          this.handleOcrResult(result);
          this.clearOcrAsyncTracking();
          return;
        }

        if (jobStatus.status === 'failed') {
          this.clearOcrAsyncTracking();
          this.ocrProcessing.set(false);
          const jobResult = (jobStatus.result as Record<string, any>) || {};
          this.ocrMessage.set((jobResult['error'] as string) || 'OCR failed');
          this.ocrMessageTone.set('error');
          return;
        }

        if (typeof jobStatus.progress === 'number') {
          this.ocrMessage.set(`Processing... ${jobStatus.progress}%`);
        } else {
          this.ocrMessage.set('Processing...');
        }
        this.ocrMessageTone.set('info');
      },
      error: (error: any) => {
        this.pollSub = null;
        this.ocrProcessing.set(false);
        this.ocrMessage.set(this.extractOcrError(error) || 'Realtime OCR updates failed');
        this.ocrMessageTone.set('error');
      },
      complete: () => {
        this.pollSub = null;
      },
    });
  }

  private clearOcrAsyncTracking(): void {
    if (this.pollSub) {
      this.pollSub.unsubscribe();
      this.pollSub = null;
    }
  }

  private handleOcrResult(status: OcrStatusResponse): void {
    this.clearOcrAsyncTracking();
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
    const previewUrl = status.previewUrl ?? (status as { preview_url?: string }).preview_url;
    if (previewUrl) {
      this.passportPreviewUrl.set(previewUrl);
    } else if (previewImage) {
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

  private buildPayload(): CustomerCreateDto {
    const rawValue = this.form.getRawValue();

    // Use a helper to format dates consistently in local time (YYYY-MM-DD)
    const formatDate = (date: Date | null) => {
      if (!date || isNaN(date.getTime())) return null;
      const year = date.getFullYear();
      const month = String(date.getMonth() + 1).padStart(2, '0');
      const day = String(date.getDate()).padStart(2, '0');
      return `${year}-${month}-${day}`;
    };

    return {
      customerType: rawValue.customer_type,
      firstName: rawValue.first_name,
      lastName: rawValue.last_name,
      companyName: rawValue.company_name,
      gender: rawValue.gender,
      nationality: rawValue.nationality,
      birthdate: formatDate(rawValue.birthdate),
      birthPlace: rawValue.birth_place,
      passportNumber: rawValue.passport_number,
      passportIssueDate: formatDate(rawValue.passport_issue_date),
      passportExpirationDate: formatDate(rawValue.passport_expiration_date),
      npwp: rawValue.npwp,
      email: rawValue.email,
      telephone: rawValue.telephone,
      whatsapp: rawValue.whatsapp,
      telegram: rawValue.telegram,
      facebook: rawValue.facebook,
      instagram: rawValue.instagram,
      twitter: rawValue.twitter,
      addressBali: rawValue.address_bali,
      addressAbroad: rawValue.address_abroad,
      notifyDocumentsExpiration: rawValue.notify_documents_expiration,
      notifyBy: rawValue.notify_by,
      active: rawValue.active,
      title: rawValue.title,
      passportMetadata: this.passportMetadata(),
    };
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
