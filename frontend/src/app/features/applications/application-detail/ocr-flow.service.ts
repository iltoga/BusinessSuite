import { computed, inject, Injectable, signal } from '@angular/core';
import { Subscription } from 'rxjs';

import { AsyncJobStatusEnum, type AsyncJob } from '@/core/api';
import {
  ApplicationsService,
  type ApplicationDocument,
  type OcrStatusResponse,
} from '@/core/services/applications.service';
import { DocumentsService } from '@/core/services/documents.service';
import { JobService } from '@/core/services/job.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { extractJobId } from '@/core/utils/async-job-contract';
import { parseApiDate } from '@/shared/utils/date-parsing';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

/**
 * Encapsulates all OCR scanning state and logic.
 * Provided at component level — each ApplicationDetailComponent gets its own instance.
 *
 * Follows the same pattern as {@link ApplicationCategorizationHandler}.
 */
@Injectable()
export class ApplicationOcrService {
  private readonly applicationsService = inject(ApplicationsService);
  private readonly documentsService = inject(DocumentsService);
  private readonly jobService = inject(JobService);
  private readonly toast = inject(GlobalToastService);

  // ─── Public state ──────────────────────────────────────────────

  readonly polling = signal(false);
  readonly status = signal<string | null>(null);
  readonly previewImage = signal<string | null>(null);
  readonly reviewOpen = signal(false);
  readonly reviewData = signal<OcrStatusResponse | null>(null);
  readonly extractedDataDialogOpen = signal(false);
  readonly extractedDataDialogText = signal('');
  readonly metadata = signal<Record<string, unknown> | null>(null);

  readonly extractedDataText = computed(() => this.buildExtractedDataText());
  readonly hasExtractedData = computed(() => this.extractedDataText() !== this.NO_DATA_TEXT);
  readonly previewExpanded = signal(false);

  // ─── Private ───────────────────────────────────────────────────

  private pollSub: Subscription | null = null;
  private readonly NO_DATA_TEXT = 'No OCR extracted data yet.';

  // ─── Public methods ────────────────────────────────────────────

  /**
   * Entry point: validate prerequisites then start the OCR pipeline.
   *
   * If no local file is selected but the document already has a remote file,
   * the remote file is downloaded first.
   */
  runOcr(document: ApplicationDocument | null, file: File | null): void {
    if (!document || !document.docType?.aiValidation) {
      return;
    }
    if (this.polling()) {
      return;
    }

    if (file) {
      this.startOcrForFile(document, file);
      return;
    }

    if (!document.fileLink) {
      this.toast.error('Select or upload a file before running OCR');
      return;
    }

    this.polling.set(true);
    this.status.set('Preparing file');

    this.documentsService.downloadDocumentFile(document.id).subscribe({
      next: (blob) => {
        const ocrFile = new File([blob], this.getOcrFileName(document, blob), {
          type: blob.type || 'application/octet-stream',
          lastModified: Date.now(),
        });
        this.startOcrForFile(document, ocrFile);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to load file for OCR');
        this.polling.set(false);
        this.status.set(null);
      },
    });
  }

  /**
   * Apply the reviewed MRZ / extracted data to the provided form patch callback.
   *
   * The caller provides a callback that receives the patch object and a reference
   * to the selected document so that the service does not depend on the component's
   * form shape.
   */
  applyOcrData(
    selectedDocument: ApplicationDocument | null,
    currentDetails: string,
    patchForm: (patch: {
      docNumber?: string;
      expirationDate?: Date | null;
      details?: string;
    }) => void,
  ): void {
    const data = this.reviewData();
    if (!data) {
      this.reviewOpen.set(false);
      return;
    }

    const patchValue: {
      docNumber?: string;
      expirationDate?: Date | null;
      details?: string;
    } = {};

    if (data.mrzData) {
      patchValue.docNumber = data.mrzData.number ?? '';
      patchValue.expirationDate = parseApiDate(data.mrzData.expirationDateYyyyMmDd);
      this.metadata.set(data.mrzData ?? {});
    }

    if (selectedDocument?.docType?.hasDetails) {
      const extractedDetails = this.buildExtractedDataText();
      if (extractedDetails && extractedDetails !== this.NO_DATA_TEXT) {
        patchValue.details = this.mergeOcrDetails(currentDetails, extractedDetails);
      }
    }

    if (Object.keys(patchValue).length > 0) {
      patchForm(patchValue);
    }
    this.reviewOpen.set(false);
  }

  dismissReview(): void {
    this.reviewOpen.set(false);
  }

  dismissExtractedDataDialog(): void {
    this.extractedDataDialogOpen.set(false);
    this.extractedDataDialogText.set('');
  }

  /**
   * Handle auto-extraction for the selected document after OCR completes.
   *
   * If the document's doc type has a details field, OCR text is merged into the form.
   * Otherwise, an extracted-data dialog is opened.
   *
   * @returns `true` if the extracted-data dialog was opened.
   */
  handleOcrExtractionForSelectedDocument(
    selectedDocument: ApplicationDocument | null,
    currentDetails: string,
    patchDetails: (merged: string) => void,
  ): boolean {
    if (!selectedDocument) {
      return false;
    }

    const extractedDetails = this.buildExtractedDataText();
    if (!extractedDetails || extractedDetails === this.NO_DATA_TEXT) {
      this.extractedDataDialogOpen.set(false);
      this.extractedDataDialogText.set('');
      return false;
    }

    if (selectedDocument.docType?.hasDetails) {
      const merged = this.mergeOcrDetails(currentDetails, extractedDetails);
      if (merged !== currentDetails) {
        patchDetails(merged);
      }
      this.extractedDataDialogOpen.set(false);
      this.extractedDataDialogText.set('');
      return false;
    }

    this.extractedDataDialogText.set(extractedDetails);
    this.extractedDataDialogOpen.set(true);
    return true;
  }

  /** Clean up subscriptions. Should be called on component destroy. */
  destroy(): void {
    this.pollSub?.unsubscribe();
    this.pollSub = null;
  }

  // ─── Private implementation ────────────────────────────────────

  private startOcrForFile(document: ApplicationDocument, file: File): void {
    this.polling.set(true);
    this.status.set('Queued');

    this.applicationsService
      .startDocumentOcr(file, {
        documentId: document.id,
        docTypeId: document.docType?.id,
      })
      .subscribe({
        next: (response) => {
          const jobId = extractJobId(response);
          if (jobId && typeof jobId === 'string') {
            this.trackOcrJob(jobId);
          } else {
            this.handleOcrResult(response as unknown as OcrStatusResponse);
          }
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to start OCR');
          this.polling.set(false);
        },
      });
  }

  private getOcrFileName(document: ApplicationDocument, blob: Blob): string {
    const link = document.fileLink ?? '';
    const basePath = link.split('?')[0]?.split('#')[0] ?? '';
    const lastSegment = basePath.split('/').filter(Boolean).pop();
    if (lastSegment) {
      try {
        return decodeURIComponent(lastSegment);
      } catch {
        return lastSegment;
      }
    }

    const extension =
      blob.type === 'application/pdf'
        ? 'pdf'
        : blob.type.startsWith('image/')
          ? (blob.type.split('/')[1] ?? 'jpg')
          : 'bin';
    return `document-${document.id}.${extension}`;
  }

  private trackOcrJob(jobId: string): void {
    this.pollSub?.unsubscribe();

    this.pollSub = this.jobService.watchJob(jobId).subscribe({
      next: (jobStatus: AsyncJob) => {
        if (jobStatus.status === AsyncJobStatusEnum.Completed) {
          const jobResult = (jobStatus.result as Record<string, any>) || {};
          const result: OcrStatusResponse = {
            ...jobResult,
            status: 'completed',
            jobId: jobStatus.jobId,
          };
          this.handleOcrResult(result);
          this.pollSub?.unsubscribe();
          return;
        }

        if (jobStatus.status === AsyncJobStatusEnum.Failed) {
          const jobResult = (jobStatus.result as Record<string, any>) || {};
          this.toast.error((jobResult['errorMessage'] as string) || 'OCR failed');
          this.polling.set(false);
          this.pollSub?.unsubscribe();
          return;
        }

        if (typeof jobStatus.progress === 'number') {
          this.status.set(`Processing ${jobStatus.progress}%`);
        } else {
          this.status.set('Processing...');
        }
      },
      error: (error: any) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to track OCR status');
        this.polling.set(false);
      },
    });
  }

  /**
   * `handleOcrResult` needs to call `handleOcrExtractionForSelectedDocument` but
   * that requires the parent component's current state (selected document, form
   * details). We store the result and let the component drive the next step via
   * a callback provided at `runOcr` time.
   */
  private ocrResultCallback: ((status: OcrStatusResponse) => void) | null = null;

  /**
   * Start OCR and register a callback that fires once results arrive.
   * The callback receives the full `OcrStatusResponse` so the parent can call
   * `handleOcrExtractionForSelectedDocument` with its own form state.
   */
  runOcrWithCallback(
    document: ApplicationDocument | null,
    file: File | null,
    onResult: (status: OcrStatusResponse) => void,
  ): void {
    this.ocrResultCallback = onResult;
    this.runOcr(document, file);
  }

  private handleOcrResult(status: OcrStatusResponse): void {
    this.polling.set(false);
    this.status.set('Completed');
    this.reviewData.set(status);

    const previewUrl = status.previewUrl;
    if (previewUrl) {
      this.previewImage.set(previewUrl);
    } else if (status.b64ResizedImage) {
      this.previewImage.set(`data:image/jpeg;base64,${status.b64ResizedImage}`);
    }

    // Callback lets the parent handle extraction + dialog using its own form state.
    if (this.ocrResultCallback) {
      this.ocrResultCallback(status);
      this.ocrResultCallback = null;
    }
  }

  private buildExtractedDataText(): string {
    const review = this.reviewData();
    const metadataVal = this.metadata();
    const structuredData = this.getStructuredOcrData(review);
    const directText = this.getDirectOcrText(review);

    if (structuredData && Object.keys(structuredData).length > 0) {
      return JSON.stringify(structuredData, null, 2);
    }

    if (directText) {
      return directText;
    }

    const extracted: Record<string, unknown> = {};
    if (review) {
      const reviewRecord = review as unknown as Record<string, unknown>;
      for (const [key, value] of Object.entries(reviewRecord)) {
        if (value === undefined || value === null || value === '') {
          continue;
        }
        if (
          key === 'jobId' ||
          key === 'status' ||
          key === 'progress' ||
          key === 'previewUrl' ||
          key === 'b64ResizedImage'
        ) {
          continue;
        }
        extracted[key] = value;
      }
    }

    if (Object.keys(extracted).length > 0) {
      return JSON.stringify(extracted, null, 2);
    }

    if (metadataVal && Object.keys(metadataVal).length > 0) {
      return JSON.stringify(metadataVal, null, 2);
    }

    return this.NO_DATA_TEXT;
  }

  private getStructuredOcrData(
    status: OcrStatusResponse | null,
  ): Record<string, string | null> | null {
    if (!status) {
      return null;
    }

    const directStructured = status.structuredData ?? null;
    if (directStructured && typeof directStructured === 'object') {
      return directStructured;
    }

    const textPayload = this.getDirectOcrText(status);
    if (!textPayload) {
      return null;
    }
    try {
      const parsed = JSON.parse(textPayload);
      if (parsed && typeof parsed === 'object' && !Array.isArray(parsed)) {
        return parsed as Record<string, string | null>;
      }
    } catch {
      return null;
    }
    return null;
  }

  private getDirectOcrText(status: OcrStatusResponse | null): string | null {
    if (!status) {
      return null;
    }
    const textValue = typeof status.resultText === 'string' ? status.resultText : null;
    if (!textValue) {
      return null;
    }
    const trimmed = textValue.trim();
    return trimmed || null;
  }

  private mergeOcrDetails(currentDetails: string, extractedDetails: string): string {
    const current = (currentDetails ?? '').trim();
    const extracted = extractedDetails.trim();
    if (!extracted) {
      return currentDetails;
    }
    if (!current) {
      return extracted;
    }
    if (current.includes(extracted)) {
      return current;
    }
    return `${current}\n\n${extracted}`;
  }
}
