import { HttpClient, HttpEvent } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { SseService } from '@/core/services/sse.service';
import { normalizeJobEnvelope } from '@/core/utils/async-job-contract';

export interface CategorizationStartResponse {
  jobId: string;
  totalFiles: number;
  status: string;
}

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

export interface CategorizationApplyResponse {
  applied: Array<{
    itemId: string;
    documentId: number;
    documentType: string;
    filename: string;
  }>;
  errors: Array<{
    itemId: string;
    error: string;
  }>;
  totalApplied: number;
  totalErrors: number;
}

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
  private readonly http = inject(HttpClient);
  private readonly sseService = inject(SseService);

  /**
   * Create categorization job first so frontend can subscribe to SSE before uploading files.
   */
  createCategorizationJob(
    applicationId: number,
    totalFiles: number,
    model?: string,
    providerOrder?: string[],
  ): Observable<CategorizationStartResponse> {
    return this.http.post<CategorizationStartResponse>(
      `/api/customer-applications/${applicationId}/categorize-documents/init/`,
      {
        totalFiles,
        model: model ?? null,
        providerOrder: providerOrder ?? null,
      },
    ).pipe(map((response) => normalizeJobEnvelope(response)));
  }

  /**
   * Upload files into an existing categorization job.
   */
  uploadFilesToJob(jobId: string, files: File[]): Observable<HttpEvent<unknown>> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));

    return this.http.post(`/api/document-categorization/${jobId}/upload/`, formData, {
      observe: 'events',
      reportProgress: true,
    });
  }

  /**
   * Connect to the SSE stream for categorization progress.
   * Returns events with type and data parsed from SSE event/data lines.
   */
  watchCategorizationJob(jobId: string): Observable<CategorizationSseEvent> {
    return this.sseService
      .connectMessages<CategorizationSseEvent['data']>(`/api/document-categorization/stream/${jobId}/`)
      .pipe(
        // Preserve the existing consumer contract: { type, data }.
        // `type` comes from SSE `event:` with fallback to "message".
        // Cursor handling is done inside SseService via SSE `id`.
        map((message) => ({ type: message.event || 'message', data: message.data })),
      );
  }

  /**
   * Apply confirmed categorization results.
   */
  applyResults(
    jobId: string,
    mappings: CategorizationApplyMapping[],
  ): Observable<CategorizationApplyResponse> {
    const payload = {
      mappings: mappings.map((mapping) => ({
        item_id: mapping.itemId,
        document_id: mapping.documentId,
      })),
    };

    return this.http.post<CategorizationApplyResponse>(
      `/api/document-categorization/${jobId}/apply/`,
      payload,
    );
  }

  /**
   * Validate a single file against its expected document type.
   */
  validateCategory(documentId: number, file: File): Observable<ValidateCategoryResponse> {
    const formData = new FormData();
    formData.append('file', file);

    return this.http.post<ValidateCategoryResponse>(
      `/api/documents/${documentId}/validate-category/`,
      formData,
    );
  }
}
