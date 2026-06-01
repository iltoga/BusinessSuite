import { HttpClient, HttpResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable, takeWhile } from 'rxjs';

import { isRecord, normalizeJobEnvelope } from '@/core/utils/async-job-contract';
import {
  createAsyncRequestMetadata,
  requestMetadataContext,
  type RequestMetadata,
} from '@/core/utils/request-metadata';
import { reconnectOnComplete, SseService } from './sse.service';

const OCR_STREAM_RECONNECT_DELAY_MS = 250;
const OCR_STREAM_ROTATION_MS = 55_000;

export interface OcrQueuedResponse {
  jobId: string;
  status: string;
  progress?: number;
  statusUrl?: string;
  streamUrl?: string;
  extractionMode?: PassportOcrExtractionMode;
  queued?: boolean;
  deduplicated?: boolean;
}

export type PassportOcrExtractionMode = 'ai' | 'ocr';

export interface OcrStatusResponse {
  jobId: string;
  status: string;
  progress?: number;
  statusUrl?: string;
  streamUrl?: string;
  resultText?: string;
  structuredData?: Record<string, string | null>;
  errorMessage?: string;
  extractionMode?: PassportOcrExtractionMode;
  mrzData?: {
    names?: string;
    surname?: string;
    sex?: string;
    nationality?: string;
    number?: string;
    dateOfBirthYyyyMmDd?: string;
    expirationDateYyyyMmDd?: string;
    passportIssueDate?: string;
    issueDateYyyyMmDd?: string;
    birthPlace?: string;
    addressAbroad?: string;
    extractionMethod?: string;
    aiConfidenceScore?: number;
    hasMismatches?: boolean;
    fieldMismatches?: Array<{ field: string; aiValue: string; mrzValue: string }>;
    mismatchSummary?: string;
  };
  aiWarning?: string;
  b64ResizedImage?: string;
  previewUrl?: string;
}

export interface DocumentOcrStatusResponse {
  jobId?: string;
  status: string;
  progress?: number;
  resultText?: string;
  structuredData?: Record<string, string | null>;
  errorMessage?: string;
}

export interface PassportOcrOptions {
  useAi?: boolean;
  saveSession?: boolean;
  previewWidth?: number;
  requestMetadata?: RequestMetadata | null;
}

@Injectable({
  providedIn: 'root',
})
export class OcrService {
  private http = inject(HttpClient);
  private sseService = inject(SseService);

  startPassportOcr(
    file: File,
    options: PassportOcrOptions = {},
  ): Observable<OcrQueuedResponse | OcrStatusResponse> {
    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', 'passport');
    formData.append('img_preview', 'true');
    formData.append('resize', 'true');
    formData.append('width', String(options.previewWidth ?? 500));
    if (options.saveSession) {
      formData.append('save_session', 'true');
    }
    formData.append('use_ai', options.useAi ? 'true' : 'false');

    const metadata = options.requestMetadata ?? createAsyncRequestMetadata();
    return this.http
      .post<OcrQueuedResponse | OcrStatusResponse>('/api/ocr/check/', formData, {
        context: requestMetadataContext(metadata),
      })
      .pipe(map((response) => normalizeJobEnvelope(response)));
  }

  getOcrStatus(statusUrl: string): Observable<OcrStatusResponse> {
    return this.getOcrStatusResponse(statusUrl).pipe(
      map((response) => normalizeJobEnvelope(response.body as OcrStatusResponse)),
    );
  }

  watchPassportOcrJob(jobId: string, _streamUrl?: string | null): Observable<OcrStatusResponse> {
    // The dedicated DRF /api/ocr/stream endpoint rejects text/event-stream
    // Accept negotiation in the local app. Use the generic SSE endpoint, which
    // the backend maps to OCRJob records and returns the same Redis stream.
    const normalizedUrl = `/api/async-jobs/status/${jobId}/`;
    return reconnectOnComplete(
      () =>
        this.sseService.connect<unknown>(normalizedUrl, {
          maxConnectionDurationMs: OCR_STREAM_ROTATION_MS,
        }),
      {
        reconnectDelayMs: OCR_STREAM_RECONNECT_DELAY_MS,
        shouldReconnect: (lastPayload) => {
          if (lastPayload === null) {
            return true;
          }

          return !this.isTerminalOcrStatus(
            this.normalizePassportOcrStreamPayload(lastPayload).status,
          );
        },
      },
    ).pipe(
      map((payload) => this.normalizePassportOcrStreamPayload(payload)),
      takeWhile((job) => !this.isTerminalOcrStatus(job.status), true),
    );
  }

  getOcrStatusResponse(statusUrl: string): Observable<HttpResponse<OcrStatusResponse>> {
    const normalizedUrl = statusUrl.replace(/^https?:\/\/[^/]+/, '');
    return this.http.get<OcrStatusResponse>(normalizedUrl, {
      observe: 'response',
    });
  }

  startDocumentOcr(
    file: File,
    options?: { documentId?: number; docTypeId?: number; requestMetadata?: RequestMetadata | null },
  ): Observable<OcrQueuedResponse | DocumentOcrStatusResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (typeof options?.documentId === 'number') {
      formData.append('document_id', String(options.documentId));
    }
    if (typeof options?.docTypeId === 'number') {
      formData.append('doc_type_id', String(options.docTypeId));
    }

    const metadata = options?.requestMetadata ?? createAsyncRequestMetadata();
    return this.http
      .post<OcrQueuedResponse | DocumentOcrStatusResponse>('/api/document-ocr/check/', formData, {
        context: requestMetadataContext(metadata),
      })
      .pipe(map((response) => normalizeJobEnvelope(response)));
  }

  getDocumentOcrStatus(statusUrl: string): Observable<DocumentOcrStatusResponse> {
    return this.getDocumentOcrStatusResponse(statusUrl).pipe(
      map((response) => normalizeJobEnvelope(response.body as DocumentOcrStatusResponse)),
    );
  }

  getDocumentOcrStatusResponse(
    statusUrl: string,
  ): Observable<HttpResponse<DocumentOcrStatusResponse>> {
    const normalizedUrl = statusUrl.replace(/^https?:\/\/[^/]+/, '');
    return this.http.get<DocumentOcrStatusResponse>(normalizedUrl, {
      observe: 'response',
    });
  }

  private isTerminalOcrStatus(status: string | null | undefined): boolean {
    const normalized = String(status ?? '')
      .trim()
      .toLowerCase();
    return normalized === 'completed' || normalized === 'failed';
  }

  private normalizePassportOcrStreamPayload(payload: unknown): OcrStatusResponse {
    const job = normalizeJobEnvelope(payload as OcrStatusResponse & { result?: unknown });
    const result = isRecord(job.result) ? job.result : {};

    return {
      ...result,
      jobId: job.jobId,
      status: job.status,
      progress: job.progress,
      extractionMode: this.normalizePassportOcrExtractionMode(
        job.extractionMode ?? result['extractionMode'],
      ),
      errorMessage:
        typeof job.errorMessage === 'string'
          ? job.errorMessage
          : typeof result['errorMessage'] === 'string'
            ? result['errorMessage']
            : undefined,
    } as OcrStatusResponse;
  }

  private normalizePassportOcrExtractionMode(
    value: unknown,
  ): PassportOcrExtractionMode | undefined {
    const mode = String(value ?? '')
      .trim()
      .toLowerCase();
    if (mode === 'ai' || mode === 'ocr') {
      return mode;
    }
    return undefined;
  }
}
