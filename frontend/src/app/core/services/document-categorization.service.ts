import { HttpEvent } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import {
  DocumentCategorizationApplyResponse as ApiDocumentCategorizationApplyResponse,
  DocumentCategorizationStartResponse as ApiDocumentCategorizationStartResponse,
  DocumentCategorizationUploadFilesResponse as ApiDocumentCategorizationUploadFilesResponse,
  CustomerApplicationsService as CustomerApplicationsApiService,
  DocumentCategorizationService as DocumentCategorizationApiService,
  DocumentsService,
} from '@/core/api';
import { reconnectOnComplete, SseService } from '@/core/services/sse.service';
import { normalizeJobEnvelope } from '@/core/utils/async-job-contract';
import { isCategorizationPipelineTerminal } from '@/core/utils/document-categorization-pipeline';
import {
  createAsyncRequestMetadata,
  requestMetadataContext,
  type RequestMetadata,
} from '@/core/utils/request-metadata';

export type CategorizationStartResponse = ApiDocumentCategorizationStartResponse;

export interface CategorizationFileResult {
  itemId: string;
  filename: string;
  status: string;
  pipelineStage?:
    | 'uploading'
    | 'uploaded'
    | 'categorizing'
    | 'categorized'
    | 'validating'
    | 'validated'
    | 'error';
  aiValidationEnabled?: boolean;
  documentType: string | null;
  documentTypeId: number | null;
  documentId: number | null;
  confidence: number;
  reasoning: string;
  error: string | null;
  errorMessage?: string | null;
  categorizationPass: number | null;
  validationStatus: 'valid' | 'invalid' | 'pending' | 'error' | null;
  validationReasoning: string | null;
  validationNegativeIssues: string[] | null;
  validationProvider?: string | null;
  validationProviderName?: string | null;
  validationModel?: string | null;
}

export interface CategorizationSseEvent {
  type: string;
  data: {
    itemId?: string;
    jobId?: string;
    index?: number;
    filename?: string;
    documentType?: string | null;
    documentTypeId?: number | null;
    documentId?: number | null;
    confidence?: number;
    reasoning?: string;
    message?: string;
    error?: string;
    errorMessage?: string;
    total?: number;
    categorizationPass?: number;
    validationStatus?: string;
    validationReasoning?: string;
    validationNegativeIssues?: string[];
    validationProvider?: string;
    validationProviderName?: string;
    validationModel?: string;
    validationConfidence?: number;
    aiValidationEnabled?: boolean;
    pipelineStage?:
      | 'uploading'
      | 'uploaded'
      | 'categorizing'
      | 'categorized'
      | 'validating'
      | 'validated'
      | 'error';
    uploadedFiles?: number;
    totalFiles?: number;
    processedFiles?: number;
    uploadedBytes?: number;
    totalBytes?: number;
    currentFile?: string | null;
    overallPercent?: number;
    phase?: 'uploading' | 'processing' | 'completed' | string;
    summary?: {
      total: number;
      success: number;
      errors: number;
    };
    results?: CategorizationFileResult[];
  };
}

export interface CategorizationApplyMapping {
  itemId: string;
  documentId: number;
}

export type CategorizationApplyResponse = ApiDocumentCategorizationApplyResponse;

const CATEGORIZATION_STREAM_RECONNECT_DELAY_MS = 250;
const CATEGORIZATION_STREAM_ROTATION_MS = 55_000;

export interface ValidateCategoryResponse {
  matches: boolean;
  expectedType: string;
  detectedType: string | null;
  confidence: number;
  reasoning: string;
  documentTypeId: number | null;
  validationStatus?: 'valid' | 'invalid' | 'error' | '';
  validationResult?: Record<string, unknown> | null;
  aiValidationEnabled?: boolean;
  validationProvider?: string | null;
  validationProviderName?: string | null;
  validationModel?: string | null;
}

@Injectable({
  providedIn: 'root',
})
export class DocumentCategorizationService {
  private readonly customerApplicationsApi = inject(CustomerApplicationsApiService);
  private readonly documentCategorizationApi = inject(DocumentCategorizationApiService);
  private readonly documentsApi = inject(DocumentsService);
  private readonly sseService = inject(SseService);

  /**
   * Create categorization job first so frontend can subscribe to SSE before uploading files.
   */
  createCategorizationJob(
    applicationId: number,
    totalFiles: number,
    model?: string,
    providerOrder?: string[],
    requestMetadata?: RequestMetadata | null,
  ): Observable<CategorizationStartResponse> {
    const metadata = requestMetadata ?? createAsyncRequestMetadata();
    return this.customerApplicationsApi
      .customerApplicationsCategorizeDocumentsInitCreate(
        {
          applicationId,
          documentCategorizationInitRequestRequest: {
            totalFiles,
            model: model ?? null,
            providerOrder: providerOrder ?? undefined,
          },
        },
        'body',
        false,
        {
          context: requestMetadataContext(metadata),
        },
      )
      .pipe(map((response) => normalizeJobEnvelope(response)));
  }

  /**
   * Upload files into an existing categorization job.
   */
  uploadFilesToJob(
    jobId: string,
    files: File[],
  ): Observable<HttpEvent<ApiDocumentCategorizationUploadFilesResponse>> {
    return this.documentCategorizationApi.documentCategorizationUploadCreate(
      {
        jobId,
        files,
      },
      'events',
      true,
    );
  }

  /**
   * Connect to the SSE stream for categorization progress.
   * Returns events with type and data parsed from SSE event/data lines.
   */
  watchCategorizationJob(jobId: string): Observable<CategorizationSseEvent> {
    return reconnectOnComplete(
      () =>
        this.sseService
          .connectMessages<CategorizationSseEvent['data']>(
            `/api/document-categorization/stream/${jobId}/`,
            {
              maxConnectionDurationMs: CATEGORIZATION_STREAM_ROTATION_MS,
            },
          )
          .pipe(map((message) => ({ type: message.event || 'message', data: message.data }))),
      {
        reconnectDelayMs: CATEGORIZATION_STREAM_RECONNECT_DELAY_MS,
        shouldReconnect: (lastEvent) =>
          lastEvent === null || !this.isCategorizationEventTerminal(lastEvent),
      },
    );
  }

  /**
   * Apply confirmed categorization results.
   */
  applyResults(
    jobId: string,
    mappings: CategorizationApplyMapping[],
  ): Observable<CategorizationApplyResponse> {
    return this.documentCategorizationApi.documentCategorizationApplyCreate({
      jobId,
      categorizationApplyRequest: {
        mappings: mappings.map((mapping) => ({
          itemId: mapping.itemId,
          documentId: mapping.documentId,
        })),
      },
    });
  }

  /**
   * Validate a single file against its expected document type.
   */
  validateCategory(documentId: number, file: File): Observable<ValidateCategoryResponse> {
    return this.documentsApi
      .documentsValidateCategoryCreate({
        documentId,
        file,
      })
      .pipe(map((response) => this.normalizeValidateCategoryResponse(response)));
  }

  private normalizeValidateCategoryResponse(
    response: Record<string, unknown>,
  ): ValidateCategoryResponse {
    return {
      matches: this.readBoolean(response['matches']),
      expectedType: this.readString(response['expectedType']) ?? '',
      detectedType: this.readString(response['detectedType']),
      confidence: this.readNumber(response['confidence']) ?? 0,
      reasoning: this.readString(response['reasoning']) ?? '',
      documentTypeId: this.readNumber(response['documentTypeId']),
      validationStatus: this.readValidationStatus(response['validationStatus']),
      validationResult: this.readRecord(response['validationResult']),
      aiValidationEnabled: this.readOptionalBoolean(response['aiValidationEnabled']),
      validationProvider: this.readString(response['validationProvider']),
      validationProviderName: this.readString(response['validationProviderName']),
      validationModel: this.readString(response['validationModel']),
    };
  }

  private readString(value: unknown): string | null {
    if (typeof value !== 'string') {
      return null;
    }

    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : null;
  }

  private readNumber(value: unknown): number | null {
    if (typeof value === 'number') {
      return Number.isFinite(value) ? value : null;
    }

    if (typeof value === 'string' && value.trim().length > 0) {
      const parsed = Number(value);
      return Number.isFinite(parsed) ? parsed : null;
    }

    return null;
  }

  private readBoolean(value: unknown): boolean {
    if (typeof value === 'boolean') {
      return value;
    }

    if (typeof value === 'string') {
      const normalized = value.trim().toLowerCase();
      if (normalized === 'true') {
        return true;
      }
      if (normalized === 'false') {
        return false;
      }
    }

    return Boolean(value);
  }

  private readOptionalBoolean(value: unknown): boolean | undefined {
    if (value === null || value === undefined) {
      return undefined;
    }

    return this.readBoolean(value);
  }

  private readRecord(value: unknown): Record<string, unknown> | null {
    if (value && typeof value === 'object' && !Array.isArray(value)) {
      return value as Record<string, unknown>;
    }

    return null;
  }

  private readValidationStatus(value: unknown): ValidateCategoryResponse['validationStatus'] {
    if (typeof value !== 'string') {
      return undefined;
    }

    const normalized = value.trim().toLowerCase();
    if (
      normalized === 'valid' ||
      normalized === 'invalid' ||
      normalized === 'error' ||
      normalized === ''
    ) {
      return normalized;
    }

    return undefined;
  }

  private isCategorizationEventTerminal(event: CategorizationSseEvent): boolean {
    const results = Array.isArray(event.data?.results) ? event.data.results : [];
    if (results.length === 0) {
      return false;
    }

    return results.every((result) => isCategorizationPipelineTerminal(result));
  }
}
