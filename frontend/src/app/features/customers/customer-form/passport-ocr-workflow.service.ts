import { inject, Injectable, signal } from '@angular/core';
import { type FormGroup } from '@angular/forms';
import { Subscription } from 'rxjs';

import { AsyncJob } from '@/core/api';
import { JobService } from '@/core/services/job.service';
import { OcrService, type OcrStatusResponse } from '@/core/services/ocr.service';
import { extractJobId } from '@/core/utils/async-job-contract';

interface AsyncJobResultPayload extends Record<string, unknown> {
  errorMessage?: string;
}

@Injectable()
export class PassportOcrWorkflowService {
  private readonly ocrService = inject(OcrService);
  private readonly jobService = inject(JobService);

  // OCR state
  readonly ocrUseAi = signal(true);
  readonly ocrProcessing = signal(false);
  readonly ocrMessage = signal<string | null>(null);
  readonly ocrMessageTone = signal<'success' | 'warning' | 'error' | 'info' | null>(null);
  readonly ocrData = signal<OcrStatusResponse | null>(null);
  readonly passportMetadata = signal<Record<string, unknown> | null>(null);
  readonly passportPreviewUrl = signal<string | null>(null);
  readonly passportPastePreviewUrl = signal<string | null>(null);
  readonly passportPasteStatus = signal<string | null>(null);

  private pollSub: Subscription | null = null;
  private form!: FormGroup;

  init(form: FormGroup): void {
    this.form = form;
  }

  destroy(): void {
    this.clearAsyncTracking();
  }

  toggleUseAi(checked: boolean): void {
    this.ocrUseAi.set(checked);
  }

  clearState(): void {
    this.ocrMessage.set(null);
    this.ocrMessageTone.set(null);
    this.passportPreviewUrl.set(null);
  }

  startImport(file: File): void {
    this.clearAsyncTracking();
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
          const jobId = extractJobId(response);
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
    this.clearAsyncTracking();

    this.pollSub = this.jobService.watchJob(jobId).subscribe({
      next: (jobStatus: AsyncJob) => {
        if (jobStatus.status === 'completed') {
          const jobResult = (jobStatus.result as AsyncJobResultPayload) || {};
          const result: OcrStatusResponse = {
            ...jobResult,
            status: 'completed',
            jobId: jobStatus.jobId,
          };
          this.handleOcrResult(result);
          this.clearAsyncTracking();
          return;
        }

        if (jobStatus.status === 'failed') {
          this.clearAsyncTracking();
          this.ocrProcessing.set(false);
          const jobResult = (jobStatus.result as AsyncJobResultPayload) || {};
          this.ocrMessage.set(
            typeof jobResult.errorMessage === 'string' ? jobResult.errorMessage : 'OCR failed',
          );
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
      error: (error: unknown) => {
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

  clearAsyncTracking(): void {
    if (this.pollSub) {
      this.pollSub.unsubscribe();
      this.pollSub = null;
    }
  }

  private handleOcrResult(status: OcrStatusResponse): void {
    this.clearAsyncTracking();
    this.ocrProcessing.set(false);
    this.ocrData.set(status);

    const mrz = status.mrzData as NonNullable<OcrStatusResponse['mrzData']> | undefined;
    if (!mrz) {
      this.ocrMessage.set('OCR completed but no data was extracted');
      this.ocrMessageTone.set('error');
      return;
    }

    const confidence =
      this.getMrzValue<number>(mrz, 'aiConfidenceScore', 'ai_confidence_score') ?? null;
    const aiWarning = status.aiWarning || null;
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

    const previewImage = status.b64ResizedImage;
    const previewUrl = status.previewUrl;
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
}
