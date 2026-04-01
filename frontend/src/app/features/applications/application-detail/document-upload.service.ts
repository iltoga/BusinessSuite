import { isPlatformBrowser } from '@angular/common';
import {
  computed,
  inject,
  Injectable,
  isDevMode,
  PLATFORM_ID,
  signal,
  type Signal,
} from '@angular/core';
import { FormBuilder } from '@angular/forms';

import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationDocument,
} from '@/core/services/applications.service';
import {
  DocumentCategorizationService,
  type ValidateCategoryResponse,
} from '@/core/services/document-categorization.service';
import { DocumentsService } from '@/core/services/documents.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { parseApiDate, toApiDate } from '@/shared/utils/date-parsing';
import {
  buildLocalFilePreview,
  inferPreviewTypeFromUrl,
} from '@/shared/utils/document-preview-source';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

export interface PreUploadValidationOutcome {
  status: 'valid' | 'invalid' | 'error';
  result: Record<string, unknown> | null;
  provider: string | null;
  providerName: string | null;
  model: string | null;
}

interface DocumentUploadHost {
  application: Signal<ApplicationDetail | null>;
  ocrMetadata: Signal<Record<string, unknown> | null>;
  replaceDocument(updated: ApplicationDocument): void;
  loadApplication(id: number, options?: { silent?: boolean }): void;
  resetOcrOnOpen(document: ApplicationDocument): void;
  resetOcrOnClose(): void;
}

/**
 * Encapsulates the document upload panel state and logic:
 * file selection, preview management, AI pre-upload validation,
 * and the upload-to-server flow.
 *
 * Provided at component level — each detail component gets its own instance.
 */
@Injectable()
export class DocumentUploadService {
  private readonly fb = inject(FormBuilder);
  private readonly applicationsService = inject(ApplicationsService);
  private readonly documentsService = inject(DocumentsService);
  private readonly categorizationService = inject(DocumentCategorizationService);
  private readonly toast = inject(GlobalToastService);
  private readonly isBrowser = isPlatformBrowser(inject(PLATFORM_ID));
  readonly isDevelopmentMode = isDevMode();

  private host!: DocumentUploadHost;

  // ─── Signals ──────────────────────────────────────────────
  readonly isOpen = signal(false);
  readonly selectedDocument = signal<ApplicationDocument | null>(null);
  readonly selectedFile = signal<File | null>(null);
  readonly uploadPreviewUrl = signal<string | null>(null);
  readonly uploadPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPreviewUrl = signal<string | null>(null);
  readonly existingPreviewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
  readonly existingPreviewLoading = signal(false);
  readonly uploadProgress = signal<number | null>(null);
  readonly isSaving = signal(false);

  readonly inlinePreviewUrl = computed(() => {
    const uploadUrl = this.uploadPreviewUrl();
    return uploadUrl ?? this.existingPreviewUrl();
  });
  readonly inlinePreviewType = computed(() => {
    if (this.uploadPreviewUrl()) {
      return this.uploadPreviewType();
    }
    return this.existingPreviewType();
  });
  readonly inlinePreviewLoading = computed(() => {
    if (this.uploadPreviewUrl()) {
      return false;
    }
    return this.existingPreviewLoading();
  });

  // AI validation
  readonly validateWithAi = signal(true);
  readonly aiValidationInProgress = signal(false);
  readonly preUploadValidationOutcome = signal<PreUploadValidationOutcome | null>(null);

  readonly preUploadValidationReason = computed(() =>
    this.buildPreUploadValidationReason(this.preUploadValidationOutcome()?.result ?? null),
  );
  readonly preUploadValidationRuntimeLabel = computed(() => {
    const outcome = this.preUploadValidationOutcome();
    if (!outcome) {
      return '';
    }
    return this.formatAiRuntimeLabel(outcome.providerName, outcome.provider, outcome.model);
  });
  readonly preUploadValidationIssues = computed(() => {
    const result = this.preUploadValidationOutcome()?.result ?? null;
    const issues = result?.['negative_issues'] ?? result?.['negativeIssues'];
    return Array.isArray(issues)
      ? issues.filter((issue): issue is string => typeof issue === 'string')
      : [];
  });
  readonly shouldShowSaveAnyway = computed(() => {
    const outcome = this.preUploadValidationOutcome();
    return (
      !!outcome &&
      outcome.status !== 'valid' &&
      this.isAiValidationEnabledForSelectedDocument() &&
      this.validateWithAi() &&
      !!this.selectedFile()
    );
  });
  readonly isAiValidationEnabledForSelectedDocument = computed(() =>
    Boolean(this.selectedDocument()?.docType?.aiValidation),
  );

  // ─── Form ─────────────────────────────────────────────────
  readonly uploadForm = this.fb.group({
    docNumber: [''],
    expirationDate: [null as Date | null],
    details: [''],
  });

  // ─── Lifecycle ────────────────────────────────────────────

  init(host: DocumentUploadHost): void {
    this.host = host;
  }

  destroy(): void {
    this.clearUploadPreview();
    this.clearExistingPreview();
    this.closeValidationStream();
  }

  // ─── Public methods ───────────────────────────────────────

  open(document: ApplicationDocument): void {
    this.selectedDocument.set(document);
    this.selectedFile.set(null);
    this.clearPreUploadValidationOutcome();
    this.clearUploadPreview();
    this.loadExistingDocumentPreview(document);
    this.uploadProgress.set(null);
    this.host.resetOcrOnOpen(document);
    this.validateWithAi.set(true);
    this.uploadForm.reset({
      docNumber: document.docNumber ?? '',
      expirationDate: parseApiDate(document.expirationDate),
      details: document.details ?? '',
    });
    this.isOpen.set(true);
  }

  close(): void {
    this.isOpen.set(false);
    this.selectedDocument.set(null);
    this.selectedFile.set(null);
    this.clearUploadPreview();
    this.clearExistingPreview();
    this.uploadProgress.set(null);
    this.host.resetOcrOnClose();
    this.closeValidationStream();
    this.clearPreUploadValidationOutcome();
  }

  onFileSelected(file: File): void {
    this.existingPreviewLoading.set(false);
    this.selectedFile.set(file);
    this.clearPreUploadValidationOutcome();
    this.setUploadPreviewFromFile(file);
  }

  onFileCleared(): void {
    this.selectedFile.set(null);
    this.clearPreUploadValidationOutcome();
    this.clearUploadPreview();
    const document = this.selectedDocument();
    if (document) {
      this.loadExistingDocumentPreview(document);
    }
  }

  onValidateWithAiChanged(checked: boolean): void {
    this.validateWithAi.set(checked);
    this.clearPreUploadValidationOutcome();
  }

  onSaveDocument(): void {
    const document = this.selectedDocument();
    if (!document) {
      return;
    }

    const formValue = this.uploadForm.getRawValue();
    const file = this.selectedFile();
    const shouldPreValidate =
      this.isAiValidationEnabledForSelectedDocument() && this.validateWithAi() && !!file;

    if (shouldPreValidate) {
      const preUploadOutcome = this.preUploadValidationOutcome();
      if (!preUploadOutcome) {
        this.runPreUploadAiValidation(document, file!, formValue);
        return;
      }
      this.uploadDocument(
        document,
        formValue,
        file,
        preUploadOutcome.status,
        preUploadOutcome.result,
      );
      return;
    }

    this.uploadDocument(document, formValue, file);
  }

  closeValidationStream(): void {
    this.aiValidationInProgress.set(false);
  }

  clearPreUploadValidationOutcome(): void {
    this.preUploadValidationOutcome.set(null);
  }

  // ─── AI validation helpers (pure logic) ───────────────────

  extractValidationAutoFillFields(validationResult: Record<string, unknown> | null): {
    expirationDate: string | null;
    docNumber: string | null;
    details: string | null;
  } {
    if (!validationResult) {
      return { expirationDate: null, docNumber: null, details: null };
    }

    const extractedExpirationDate =
      typeof (
        validationResult['extracted_expiration_date'] ?? validationResult['extractedExpirationDate']
      ) === 'string'
        ? ((validationResult['extracted_expiration_date'] ??
            validationResult['extractedExpirationDate']) as string)
        : null;
    const extractedDocNumber =
      typeof (
        validationResult['extracted_doc_number'] ?? validationResult['extractedDocNumber']
      ) === 'string'
        ? (
            (validationResult['extracted_doc_number'] ??
              validationResult['extractedDocNumber']) as string
          ).trim() || null
        : null;
    const extractedDetails =
      typeof (
        validationResult['extracted_details_markdown'] ??
        validationResult['extractedDetailsMarkdown']
      ) === 'string'
        ? (
            (validationResult['extracted_details_markdown'] ??
              validationResult['extractedDetailsMarkdown']) as string
          ).trim() || null
        : null;

    return {
      expirationDate: extractedExpirationDate,
      docNumber: extractedDocNumber,
      details: extractedDetails,
    };
  }

  mergeUploadFormWithValidationExtraction(
    payload: {
      docNumber: string | null;
      expirationDate: string | null;
      details: string | null;
    },
    validationResult: Record<string, unknown> | null,
  ): {
    docNumber: string | null;
    expirationDate: string | null;
    details: string | null;
  } {
    const extracted = this.extractValidationAutoFillFields(validationResult);

    return {
      expirationDate: extracted.expirationDate || payload.expirationDate || null,
      docNumber: extracted.docNumber || payload.docNumber || null,
      details: payload.details || extracted.details || null,
    };
  }

  applyValidationExtractionToUploadForm(validationResult: Record<string, unknown> | null): void {
    const extracted = this.extractValidationAutoFillFields(validationResult);
    const patchValue: {
      docNumber?: string;
      expirationDate?: Date | null;
      details?: string;
    } = {};

    if (extracted.docNumber) {
      patchValue.docNumber = extracted.docNumber;
    }

    if (extracted.expirationDate) {
      patchValue.expirationDate = parseApiDate(extracted.expirationDate);
    }

    const currentDetails = this.uploadForm.getRawValue().details?.trim() ?? '';
    if (!currentDetails && extracted.details) {
      patchValue.details = extracted.details;
    }

    if (Object.keys(patchValue).length > 0) {
      this.uploadForm.patchValue(patchValue);
    }
  }

  buildPreUploadValidationReason(result: Record<string, unknown> | null): string {
    if (!result) {
      return '';
    }
    const negativeIssues = result['negative_issues'] ?? result['negativeIssues'];
    const issues = Array.isArray(negativeIssues)
      ? negativeIssues.filter((issue): issue is string => typeof issue === 'string')
      : [];
    if (issues.length > 0) {
      return issues.join('; ');
    }
    return String(result['reasoning'] ?? '');
  }

  normalizeValidationResultShape(result: Record<string, unknown>): Record<string, unknown> {
    const normalized: Record<string, unknown> = { ...result };
    if ('negativeIssues' in result && !('negative_issues' in result)) {
      normalized['negative_issues'] = result['negativeIssues'];
    }
    if ('positiveAnalysis' in result && !('positive_analysis' in result)) {
      normalized['positive_analysis'] = result['positiveAnalysis'];
    }
    if ('extractedExpirationDate' in result && !('extracted_expiration_date' in result)) {
      normalized['extracted_expiration_date'] = result['extractedExpirationDate'];
    }
    if ('extractedDocNumber' in result && !('extracted_doc_number' in result)) {
      normalized['extracted_doc_number'] = result['extractedDocNumber'];
    }
    if ('extractedDetailsMarkdown' in result && !('extracted_details_markdown' in result)) {
      normalized['extracted_details_markdown'] = result['extractedDetailsMarkdown'];
    }
    if ('aiProvider' in result && !('ai_provider' in result)) {
      normalized['ai_provider'] = result['aiProvider'];
    }
    if ('aiProviderName' in result && !('ai_provider_name' in result)) {
      normalized['ai_provider_name'] = result['aiProviderName'];
    }
    if ('aiModel' in result && !('ai_model' in result)) {
      normalized['ai_model'] = result['aiModel'];
    }
    return normalized;
  }

  extractValidationRuntimeMetadata(source: Record<string, unknown> | null): {
    provider: string | null;
    providerName: string | null;
    model: string | null;
  } {
    if (!source) {
      return { provider: null, providerName: null, model: null };
    }

    const provider = this.readOptionalString(
      source['validationProvider'] ??
        source['validation_provider'] ??
        source['aiProvider'] ??
        source['ai_provider'],
    );
    const providerName = this.readOptionalString(
      source['validationProviderName'] ??
        source['validation_provider_name'] ??
        source['aiProviderName'] ??
        source['ai_provider_name'],
    );
    const model = this.readOptionalString(
      source['validationModel'] ??
        source['validation_model'] ??
        source['aiModel'] ??
        source['ai_model'],
    );

    return { provider, providerName: providerName ?? provider, model };
  }

  formatAiRuntimeLabel(
    providerName: string | null,
    provider: string | null,
    model: string | null,
  ): string {
    const providerLabel = (providerName ?? provider ?? '').trim();
    const modelLabel = (model ?? '').trim();

    if (providerLabel && modelLabel) {
      return `${providerLabel} / ${modelLabel}`;
    }
    return providerLabel || modelLabel;
  }

  // ─── Preview management ───────────────────────────────────

  setUploadPreviewFromFile(file: File): void {
    this.clearUploadPreview();
    const preview = buildLocalFilePreview(file);
    this.uploadPreviewType.set(preview.type);
    this.uploadPreviewUrl.set(preview.url);
  }

  loadExistingDocumentPreview(document: ApplicationDocument): void {
    this.clearExistingPreview();
    if (!document.fileLink) {
      return;
    }
    this.existingPreviewLoading.set(true);

    this.documentsService.downloadDocumentFile(document.id).subscribe({
      next: (blob) => {
        if (this.selectedDocument()?.id !== document.id) {
          this.existingPreviewLoading.set(false);
          return;
        }

        const url = URL.createObjectURL(blob);
        const mime = (blob.type || '').toLowerCase();
        const urlType = inferPreviewTypeFromUrl(document.fileLink);

        let type: 'image' | 'pdf' | 'unknown' = 'unknown';
        if (mime.startsWith('image/')) {
          type = 'image';
        } else if (mime === 'application/pdf') {
          type = 'pdf';
        } else {
          type = urlType;
        }

        if (type === 'unknown') {
          URL.revokeObjectURL(url);
          this.existingPreviewLoading.set(false);
          return;
        }

        this.existingPreviewType.set(type);
        this.existingPreviewUrl.set(url);
        this.existingPreviewLoading.set(false);
      },
      error: () => {
        this.clearExistingPreview();
        this.existingPreviewLoading.set(false);
      },
    });
  }

  clearUploadPreview(): void {
    const url = this.uploadPreviewUrl();
    if (url && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        // ignore
      }
    }
    this.uploadPreviewUrl.set(null);
    this.uploadPreviewType.set('unknown');
  }

  clearExistingPreview(): void {
    const url = this.existingPreviewUrl();
    if (url && url.startsWith('blob:')) {
      try {
        URL.revokeObjectURL(url);
      } catch (e) {
        // ignore
      }
    }
    this.existingPreviewUrl.set(null);
    this.existingPreviewType.set('unknown');
    this.existingPreviewLoading.set(false);
  }

  // ─── Private helpers ──────────────────────────────────────

  private readOptionalString(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }
    const normalized = value.trim();
    return normalized || null;
  }

  private runPreUploadAiValidation(
    document: ApplicationDocument,
    file: File,
    formValue: ReturnType<typeof this.uploadForm.getRawValue>,
  ): void {
    this.isSaving.set(true);
    this.aiValidationInProgress.set(true);
    this.uploadProgress.set(null);

    this.categorizationService.validateCategory(document.id, file).subscribe({
      next: (response: ValidateCategoryResponse) => {
        const outcome = this.normalizePreUploadValidationOutcome(response);
        this.preUploadValidationOutcome.set(outcome);
        this.applyValidationExtractionToUploadForm(outcome.result);
        this.aiValidationInProgress.set(false);

        if (outcome.status === 'valid') {
          this.uploadDocument(document, formValue, file, outcome.status, outcome.result);
          return;
        }

        this.isSaving.set(false);
        const runtimeLabel = this.formatAiRuntimeLabel(
          outcome.providerName,
          outcome.provider,
          outcome.model,
        );
        const runtimeSuffix = this.isDevelopmentMode && runtimeLabel ? ` [${runtimeLabel}]` : '';
        this.toast.error(
          `AI validation failed${runtimeSuffix}: ${this.buildPreUploadValidationReason(outcome.result) || 'See details below.'}`,
        );
      },
      error: (error: unknown) => {
        const message = extractServerErrorMessage(error) || 'AI validation failed';
        const rawErrorPayload =
          error && typeof error === 'object' && 'error' in error
            ? (error as { error?: unknown }).error
            : null;
        const runtime = this.extractValidationRuntimeMetadata(
          rawErrorPayload && typeof rawErrorPayload === 'object'
            ? (rawErrorPayload as Record<string, unknown>)
            : null,
        );
        this.preUploadValidationOutcome.set({
          status: 'error',
          result: {
            valid: false,
            confidence: 0,
            positive_analysis: '',
            negative_issues: [message],
            reasoning: message,
            extracted_expiration_date: null,
            extracted_doc_number: null,
            extracted_details_markdown: null,
            ai_provider: runtime.provider,
            ai_provider_name: runtime.providerName,
            ai_model: runtime.model,
          },
          provider: runtime.provider,
          providerName: runtime.providerName,
          model: runtime.model,
        });
        this.aiValidationInProgress.set(false);
        this.isSaving.set(false);
        this.toast.error(message);
      },
    });
  }

  private uploadDocument(
    document: ApplicationDocument,
    formValue: ReturnType<typeof this.uploadForm.getRawValue>,
    file: File | null,
    aiValidationStatusOverride?: '' | 'valid' | 'invalid' | 'error',
    aiValidationResultOverride?: Record<string, unknown> | null,
  ): void {
    this.isSaving.set(true);
    this.uploadProgress.set(0);

    const mergedPayload = this.mergeUploadFormWithValidationExtraction(
      {
        docNumber: formValue.docNumber || null,
        expirationDate: toApiDate(formValue.expirationDate),
        details: formValue.details || null,
      },
      aiValidationResultOverride ?? null,
    );
    const persistedAiValidationResultOverride =
      aiValidationStatusOverride === 'invalid' ? aiValidationResultOverride : null;

    this.applicationsService
      .updateDocument(
        document.id,
        {
          docNumber: mergedPayload.docNumber,
          expirationDate: mergedPayload.expirationDate,
          details: mergedPayload.details,
          metadata: this.host.ocrMetadata(),
        },
        file,
        false,
        aiValidationStatusOverride,
        persistedAiValidationResultOverride,
      )
      .subscribe({
        next: (state) => {
          if (state.state === 'progress') {
            this.uploadProgress.set(state.progress);
          } else {
            this.uploadProgress.set(state.progress);
            this.host.replaceDocument(state.document);
            const app = this.host.application();
            if (app) {
              this.host.loadApplication(app.id, { silent: true });
            }
            this.toast.success('Document updated');
            this.isSaving.set(false);
            this.close();
          }
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to update document');
          this.aiValidationInProgress.set(false);
          this.isSaving.set(false);
        },
      });
  }

  private normalizePreUploadValidationOutcome(
    response: ValidateCategoryResponse,
  ): PreUploadValidationOutcome {
    const responseRecord = response as unknown as Record<string, unknown>;
    const rawStatus = String(responseRecord['validationStatus'] ?? '')
      .trim()
      .toLowerCase();
    let status: 'valid' | 'invalid' | 'error';
    if (rawStatus === 'valid' || rawStatus === 'invalid' || rawStatus === 'error') {
      status = rawStatus;
    } else {
      status = response.matches ? 'valid' : 'invalid';
    }

    const existingResult = responseRecord['validationResult'];
    const result =
      existingResult && typeof existingResult === 'object'
        ? this.normalizeValidationResultShape(existingResult as Record<string, unknown>)
        : {
            valid: status === 'valid',
            confidence: Number(response.confidence ?? 0),
            positive_analysis: status === 'valid' ? String(response.reasoning ?? '') : '',
            negative_issues:
              status === 'invalid'
                ? [String(response.reasoning ?? 'Validation failed')].filter(Boolean)
                : [],
            reasoning: String(response.reasoning ?? ''),
            extracted_expiration_date: null,
            extracted_doc_number: null,
            extracted_details_markdown: null,
          };

    const runtimeFromResponse = this.extractValidationRuntimeMetadata(responseRecord);
    const runtimeFromResult = this.extractValidationRuntimeMetadata(result);
    const provider = runtimeFromResponse.provider ?? runtimeFromResult.provider;
    const providerName =
      runtimeFromResponse.providerName ?? runtimeFromResult.providerName ?? provider;
    const model = runtimeFromResponse.model ?? runtimeFromResult.model;

    if (result) {
      if (provider && !result['ai_provider']) {
        result['ai_provider'] = provider;
      }
      if (providerName && !result['ai_provider_name']) {
        result['ai_provider_name'] = providerName;
      }
      if (model && !result['ai_model']) {
        result['ai_model'] = model;
      }
    }

    return { status, result, provider, providerName, model };
  }
}
