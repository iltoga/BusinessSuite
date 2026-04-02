import { extractJobId } from '@/core/utils/async-job-contract';
import { createAsyncRequestMetadata, requestMetadataContext } from '@/core/utils/request-metadata';
import { ZardButtonComponent } from '@/shared/components/button';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { ZardIconComponent } from '@/shared/components/icon';
import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  inject,
  OnDestroy,
  OnInit,
  signal,
} from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Router } from '@angular/router';
import { firstValueFrom, Subscription } from 'rxjs';
import { environment } from '../../../../environments/environment';
import { CustomersService } from '../../../core/services/customers.service';
import { JobService } from '../../../core/services/job.service';
import { GlobalToastService } from '../../../core/services/toast.service';
import { AppDatePipe } from '../../../shared/pipes/app-date-pipe';
import { HelpService } from '../../../shared/services/help.service';
import { buildLocalFilePreview } from '../../../shared/utils/document-preview-source';
import { extractServerErrorMessage } from '../../../shared/utils/form-errors';
import { AsyncJobStatusEnum } from '../../../core/api';

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === 'object' && value !== null && !Array.isArray(value);
}

function readField(record: Record<string, unknown>, ...keys: string[]): unknown {
  for (const key of keys) {
    if (Object.prototype.hasOwnProperty.call(record, key)) {
      const value = record[key];
      if (value !== null && value !== undefined) {
        return value;
      }
    }
  }
  return undefined;
}

function readString(record: Record<string, unknown>, ...keys: string[]): string | null {
  const value = readField(record, ...keys);
  if (typeof value === 'string') {
    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }
  if (typeof value === 'number' || typeof value === 'boolean') {
    return String(value);
  }
  return null;
}

function readNumber(record: Record<string, unknown>, ...keys: string[]): number | null {
  const value = readField(record, ...keys);
  if (typeof value === 'number' && Number.isFinite(value)) {
    return value;
  }
  if (typeof value === 'string' && value.trim().length > 0) {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }
  return null;
}

function readBoolean(record: Record<string, unknown>, ...keys: string[]): boolean | null {
  const value = readField(record, ...keys);
  if (typeof value === 'boolean') {
    return value;
  }
  if (typeof value === 'number') {
    return value !== 0;
  }
  if (typeof value === 'string') {
    const normalized = value.trim().toLowerCase();
    if (['true', '1', 'yes'].includes(normalized)) {
      return true;
    }
    if (['false', '0', 'no'].includes(normalized)) {
      return false;
    }
  }
  return null;
}

function readStringArray(record: Record<string, unknown>, ...keys: string[]): string[] | null {
  const value = readField(record, ...keys);
  if (!Array.isArray(value)) {
    return null;
  }

  const items = value.map((item) => String(item ?? '').trim()).filter((item) => item.length > 0);
  return items.length > 0 ? items : null;
}

interface PassportExtractedData {
  first_name?: string | null;
  last_name?: string | null;
  nationality?: string | null;
  nationality_code?: string | null;
  gender?: string | null;
  date_of_birth?: string | null;
  birth_place?: string | null;
  passport_number?: string | null;
  passport_issue_date?: string | null;
  expiration_date?: string | null;
  address_abroad?: string | null;
  confidence_score?: number | null;
}

interface CustomerMatchCandidate {
  id: number;
  first_name?: string | null;
  last_name?: string | null;
  full_name?: string | null;
  passport_number?: string | null;
  passport_issue_date?: string | null;
  passport_expiration_date?: string | null;
  nationality_code?: string | null;
  nationality_name?: string | null;
  match_kind?: string | null;
  passport_status?: 'missing' | 'present' | null;
  similarity?: number | null;
}

interface CustomerMatchResult {
  status:
    | 'passport_found'
    | 'exact_name_found'
    | 'similar_name_found'
    | 'no_match'
    | 'insufficient_data'
    | 'error';
  message: string;
  passport_number?: string | null;
  exact_matches: CustomerMatchCandidate[];
  similar_matches: CustomerMatchCandidate[];
  recommended_action: 'update_customer' | 'choose_customer' | 'create_customer' | 'none';
}

function normalizePassportExtractedData(value: unknown): PassportExtractedData | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    first_name: readString(value, 'first_name', 'firstName'),
    last_name: readString(value, 'last_name', 'lastName'),
    nationality: readString(value, 'nationality'),
    nationality_code: readString(value, 'nationality_code', 'nationalityCode'),
    gender: readString(value, 'gender'),
    date_of_birth: readString(value, 'date_of_birth', 'dateOfBirth'),
    birth_place: readString(value, 'birth_place', 'birthPlace'),
    passport_number: readString(value, 'passport_number', 'passportNumber'),
    passport_issue_date: readString(value, 'passport_issue_date', 'passportIssueDate'),
    expiration_date: readString(
      value,
      'expiration_date',
      'passport_expiration_date',
      'expirationDate',
      'passportExpirationDate',
    ),
    address_abroad: readString(value, 'address_abroad', 'addressAbroad'),
    confidence_score: readNumber(value, 'confidence_score', 'confidenceScore'),
  };
}

function normalizeCustomerMatchCandidate(value: unknown): CustomerMatchCandidate | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    id: readNumber(value, 'id') ?? 0,
    first_name: readString(value, 'first_name', 'firstName'),
    last_name: readString(value, 'last_name', 'lastName'),
    full_name: readString(value, 'full_name', 'fullName'),
    passport_number: readString(value, 'passport_number', 'passportNumber'),
    passport_issue_date: readString(value, 'passport_issue_date', 'passportIssueDate'),
    passport_expiration_date: readString(
      value,
      'passport_expiration_date',
      'passportExpirationDate',
    ),
    nationality_code: readString(value, 'nationality_code', 'nationalityCode'),
    nationality_name: readString(value, 'nationality_name', 'nationalityName'),
    match_kind: readString(value, 'match_kind', 'matchKind'),
    passport_status:
      (readString(value, 'passport_status', 'passportStatus') as 'missing' | 'present' | null) ??
      null,
    similarity: readNumber(value, 'similarity'),
  };
}

function normalizeCustomerMatch(value: unknown): CustomerMatchResult | null {
  if (!isRecord(value)) {
    return null;
  }

  const exactMatches = readField(value, 'exact_matches', 'exactMatches');
  const similarMatches = readField(value, 'similar_matches', 'similarMatches');

  return {
    status: (readString(value, 'status') as CustomerMatchResult['status']) ?? 'error',
    message: readString(value, 'message') ?? '',
    passport_number: readString(value, 'passport_number', 'passportNumber'),
    exact_matches: Array.isArray(exactMatches)
      ? exactMatches
          .map((candidate) => normalizeCustomerMatchCandidate(candidate))
          .filter((candidate): candidate is CustomerMatchCandidate => candidate !== null)
      : [],
    similar_matches: Array.isArray(similarMatches)
      ? similarMatches
          .map((candidate) => normalizeCustomerMatchCandidate(candidate))
          .filter((candidate): candidate is CustomerMatchCandidate => candidate !== null)
      : [],
    recommended_action:
      (readString(value, 'recommended_action', 'recommendedAction') as
        | CustomerMatchResult['recommended_action']
        | null) ?? 'none',
  };
}

export function normalizePassportCheckResult(value: unknown): PassportCheckResult | null {
  if (!isRecord(value)) {
    return null;
  }

  return {
    is_valid: readBoolean(value, 'is_valid', 'isValid') ?? false,
    method_used: readString(value, 'method_used', 'methodUsed') ?? undefined,
    model_used: readString(value, 'model_used', 'modelUsed') ?? undefined,
    passport_data:
      normalizePassportExtractedData(readField(value, 'passport_data', 'passportData')) ??
      undefined,
    rejection_code: readString(value, 'rejection_code', 'rejectionCode') ?? undefined,
    rejection_reason: readString(value, 'rejection_reason', 'rejectionReason') ?? undefined,
    rejection_reasons: readStringArray(value, 'rejection_reasons', 'rejectionReasons') ?? undefined,
    customer_match:
      normalizeCustomerMatch(readField(value, 'customer_match', 'customerMatch')) ?? undefined,
  };
}

interface PassportCheckResult {
  is_valid: boolean;
  method_used?: string;
  model_used?: string;
  passport_data?: PassportExtractedData;
  rejection_code?: string;
  rejection_reason?: string;
  rejection_reasons?: string[];
  customer_match?: CustomerMatchResult;
}

@Component({
  selector: 'app-passport-check',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ZardButtonComponent,
    ZardIconComponent,
    FileUploadComponent,
    AppDatePipe,
  ],
  templateUrl: './passport-check.component.html',
  styleUrls: ['./passport-check.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PassportCheckComponent implements OnInit, OnDestroy {
  private readonly customersService = inject(CustomersService);
  private readonly http = inject(HttpClient);
  private readonly jobService = inject(JobService);
  private readonly toast = inject(GlobalToastService);
  private readonly helpService = inject(HelpService);
  private readonly router = inject(Router);
  private jobProgressSubscription: Subscription | null = null;

  readonly selectedFile = signal<File | null>(null);
  readonly previewUrl = signal<string | null>(null);
  readonly previewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly method = signal<'ai' | 'hybrid'>('hybrid');

  readonly isChecking = signal(false);
  readonly progress = signal(0);
  readonly progressMessage = signal('');
  readonly processSteps = signal<string[]>([]);

  readonly result = signal<PassportCheckResult | null>(null);
  readonly actionInProgress = signal(false);
  readonly actionTargetCustomerId = signal<number | null>(null);

  readonly customerMatch = computed<CustomerMatchResult | null>(
    () => this.result()?.customer_match ?? null,
  );

  ngOnInit() {
    this.helpService.register('/utils/passport-check', {
      id: '/utils/passport-check',
      briefExplanation:
        'This tool allows you to verify if a passport image meets the requirements for uploading to the Indonesian immigration website.',
      details:
        'AI: Uses deterministic OpenCV quality checks plus Google Gemini analysis. Hybrid: Runs deterministic checks, then AI with additional decision context for stricter validation.',
    });
    this.helpService.setContextForPath('/utils/passport-check');
  }

  ngOnDestroy(): void {
    this.stopProgressStream();
    this.clearPreviewUrl();
  }

  onFileSelected(file: File) {
    this.selectedFile.set(file);
    this.clearPreviewUrl();
    const preview = buildLocalFilePreview(file);
    this.previewUrl.set(preview.url);
    this.previewType.set(preview.type);

    this.result.set(null);
    this.processSteps.set([]);
    this.actionInProgress.set(false);
    this.actionTargetCustomerId.set(null);
  }

  onFileCleared() {
    this.stopProgressStream();
    this.selectedFile.set(null);
    this.clearPreviewUrl();
    this.previewType.set('unknown');
    this.result.set(null);
    this.processSteps.set([]);
    this.actionInProgress.set(false);
    this.actionTargetCustomerId.set(null);
  }

  private clearPreviewUrl() {
    const url = this.previewUrl();
    if (url && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch {}
    }
    this.previewUrl.set(null);
  }

  async checkPassport() {
    const file = this.selectedFile();
    if (!file) return;

    this.stopProgressStream();
    this.isChecking.set(true);
    this.progress.set(0);
    this.progressMessage.set('Starting verification...');
    this.processSteps.set([]);
    this.result.set(null);
    this.actionInProgress.set(false);
    this.actionTargetCustomerId.set(null);

    try {
      const formData = new FormData();
      formData.append('file', file, file.name);
      formData.append('method', this.method());

      const response = await firstValueFrom(
        this.http.post<unknown>(`${environment.apiUrl}/api/customers/check-passport/`, formData, {
          context: requestMetadataContext(createAsyncRequestMetadata()),
          withCredentials: true,
        }),
      );

      const jobId = extractJobId(response);
      if (jobId) {
        this.listenToJobProgress(jobId);
      } else {
        this.toast.error('Passport check started but no job id was returned');
        this.isChecking.set(false);
      }
    } catch (error) {
      const message = extractServerErrorMessage(error) || 'Failed to start passport check';
      this.toast.error(message);
      this.isChecking.set(false);
    }
  }

  private listenToJobProgress(jobId: string) {
    this.stopProgressStream();
    this.jobProgressSubscription = this.jobService.watchJob(jobId).subscribe({
      next: (job: any) => {
        if (job?.errorMessage) {
          this.isChecking.set(false);
          this.toast.error(String(job.errorMessage));
          this.stopProgressStream();
          return;
        }

        this.progress.set(Number(job?.progress ?? 0));
        const message = String(job?.message ?? 'Processing...');
        this.progressMessage.set(message);
        this.appendProcessStep(message);

        if (job?.status === AsyncJobStatusEnum.Completed) {
          this.isChecking.set(false);
          this.result.set(normalizePassportCheckResult(job?.result));
          this.stopProgressStream();
        } else if (job?.status === AsyncJobStatusEnum.Failed) {
          this.isChecking.set(false);
          this.toast.error(job?.errorMessage || 'Verification failed');
          this.stopProgressStream();
        }
      },
      error: () => {
        this.isChecking.set(false);
        this.toast.error('Connection to server lost');
        this.stopProgressStream();
      },
    });
  }

  private stopProgressStream() {
    this.jobProgressSubscription?.unsubscribe();
    this.jobProgressSubscription = null;
  }

  private appendProcessStep(message: string) {
    if (!message) return;
    const trimmed = message.trim();
    if (!trimmed) return;

    this.processSteps.update((steps) => {
      if (steps[steps.length - 1] === trimmed || steps.includes(trimmed)) {
        return steps;
      }
      return [...steps, trimmed];
    });
  }

  isUpdatingCustomer(customerId: number): boolean {
    return this.actionInProgress() && this.actionTargetCustomerId() === customerId;
  }

  async updateCustomer(customerId: number) {
    const file = this.selectedFile();
    const data = this.result()?.passport_data;

    if (!file || !data) {
      this.toast.error('Missing passport file or extracted data');
      return;
    }

    this.actionInProgress.set(true);
    this.actionTargetCustomerId.set(customerId);

    try {
      const payload = this.buildCustomerFormData(data, file, 'update');
      await firstValueFrom(this.customersService.updateCustomer(customerId, payload));
      this.toast.success('Customer updated successfully');
      await this.router.navigate(['/customers', customerId, 'edit']);
    } catch (error) {
      const message = extractServerErrorMessage(error) || 'Failed to update customer';
      this.toast.error(message);
    } finally {
      this.actionInProgress.set(false);
      this.actionTargetCustomerId.set(null);
    }
  }

  async createNewCustomer() {
    const file = this.selectedFile();
    const data = this.result()?.passport_data;

    if (!file || !data) {
      this.toast.error('Missing passport file or extracted data');
      return;
    }

    this.actionInProgress.set(true);
    this.actionTargetCustomerId.set(null);

    try {
      const payload = this.buildCustomerFormData(data, file, 'create');
      const customer = await firstValueFrom(this.customersService.createCustomer(payload));
      this.toast.success('Customer created successfully');
      await this.router.navigate(['/customers', customer.id, 'edit']);
    } catch (error) {
      const message = extractServerErrorMessage(error) || 'Failed to create customer';
      this.toast.error(message);
    } finally {
      this.actionInProgress.set(false);
      this.actionTargetCustomerId.set(null);
    }
  }

  customerMatchSummary(match: CustomerMatchResult | null): string {
    if (!match) {
      return '';
    }

    if (match.message) {
      return match.message;
    }

    if (match.status === 'passport_found') {
      return 'A customer with this passport already exists.';
    }

    if (match.status === 'exact_name_found') {
      return 'Exact customer name match found. You can update customer data with this passport.';
    }

    if (match.status === 'similar_name_found') {
      return 'Similar names found. Review and pick the right customer to update.';
    }

    if (match.status === 'no_match') {
      return 'No existing customer matched. You can create a new customer with this passport.';
    }

    if (match.status === 'insufficient_data') {
      return 'Not enough extracted data to run matching.';
    }

    return 'Customer matching could not be completed.';
  }

  private buildCustomerFormData(
    passportData: PassportExtractedData,
    file: File,
    mode: 'create' | 'update',
  ): FormData {
    const firstName = this.normalizeName(passportData.first_name);
    const lastName = this.normalizeName(passportData.last_name);
    const requireFullName = mode === 'create';

    if (requireFullName && (!firstName || !lastName)) {
      throw new Error(
        'Cannot create customer: first and last name are required from passport extraction.',
      );
    }

    const payload: Record<string, unknown> = {
      ...(mode === 'create' ? { customerType: 'person' } : {}),
      firstName,
      lastName,
      nationality: this.normalizeNationalityCode(
        passportData.nationality_code ?? passportData.nationality,
      ),
      gender: this.normalizeGender(passportData.gender),
      birthdate: this.normalizeDate(passportData.date_of_birth),
      birthPlace: this.normalizeText(passportData.birth_place),
      addressAbroad: this.normalizeText(passportData.address_abroad),
      passportNumber: this.normalizePassportNumber(passportData.passport_number),
      passportIssueDate: this.normalizeDate(passportData.passport_issue_date),
      passportExpirationDate: this.normalizeDate(passportData.expiration_date),
      passportMetadata: passportData,
    };

    const formData = new FormData();
    Object.entries(payload).forEach(([key, value]) => {
      if (value === null || value === undefined || value === '') {
        return;
      }
      if (typeof value === 'object') {
        formData.append(key, JSON.stringify(value));
      } else {
        formData.append(key, String(value));
      }
    });

    formData.append('passport_file', file, file.name);
    return formData;
  }

  private normalizeText(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.trim();
    return normalized ? normalized : null;
  }

  private normalizeName(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.replace(/\s+/g, ' ').trim();
    return normalized ? normalized : null;
  }

  private normalizePassportNumber(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.replace(/\s+/g, '').trim().toUpperCase();
    return normalized ? normalized : null;
  }

  private normalizeNationalityCode(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.replace(/\s+/g, '').trim().toUpperCase();
    return /^[A-Z]{3}$/.test(normalized) ? normalized : null;
  }

  private normalizeGender(value: unknown): 'M' | 'F' | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.trim().toUpperCase();
    if (normalized === 'M' || normalized === 'F') {
      return normalized;
    }
    return null;
  }

  private normalizeDate(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.trim();
    return /^\d{4}-\d{2}-\d{2}$/.test(normalized) ? normalized : null;
  }

  getDisplayRejectionReason(): string {
    const result = this.result();
    if (!result) {
      return '';
    }

    const orderedReasons = Array.isArray(result.rejection_reasons)
      ? result.rejection_reasons
          .map((value: unknown) => String(value ?? '').trim())
          .filter((value: string) => value.length > 0)
      : [];
    if (orderedReasons.length > 0) {
      return orderedReasons.join(' | ');
    }

    if (result.rejection_code === 'image_blurry') {
      return 'Passport image is blurry. Please upload a sharp image where all text and MRZ are clearly readable.';
    }

    if (result.rejection_code === 'mrz_incomplete') {
      return (
        result.rejection_reason ||
        'MRZ is incomplete (only part of the bottom zone is visible/readable). Please upload the full passport page with both full MRZ lines.'
      );
    }

    if (result.rejection_code === 'mrz_cropped') {
      return 'MRZ zone is cropped/incomplete. Please upload a full passport image where both MRZ lines are fully visible and readable.';
    }

    if (result.rejection_code === 'invalid_name') {
      return 'Extracted first/last name looks invalid. Please upload a clearer image of the complete passport biodata page.';
    }

    if (result.rejection_code === 'invalid_passport_number') {
      return result.rejection_reason || 'Extracted passport number is invalid.';
    }

    if (result.rejection_code === 'invalid_nationality') {
      return 'Extracted nationality code is invalid. Please use a clearer full-page passport image.';
    }

    if (result.rejection_code === 'missing_essential_fields') {
      return 'Essential fields are missing (name, passport number, nationality). The image quality/completeness is insufficient.';
    }

    return result.rejection_reason || 'Verification failed.';
  }
}
