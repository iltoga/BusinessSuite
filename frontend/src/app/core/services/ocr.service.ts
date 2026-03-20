import { HttpClient, HttpResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { normalizeJobEnvelope } from '@/core/utils/async-job-contract';

export interface OcrQueuedResponse {
  jobId: string;
  status: string;
  progress?: number;
  statusUrl?: string;
  streamUrl?: string;
  queued?: boolean;
  deduplicated?: boolean;
}

export interface OcrStatusResponse {
  jobId: string;
  status: string;
  progress?: number;
  resultText?: string;
  structuredData?: Record<string, string | null>;
  errorMessage?: string;
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
}

@Injectable({
  providedIn: 'root',
})
export class OcrService {
  private http = inject(HttpClient);

  startPassportOcr(
    file: File,
    options: PassportOcrOptions,
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
    if (options.useAi) {
      formData.append('use_ai', 'true');
    }

    return this.http.post<OcrQueuedResponse | OcrStatusResponse>('/api/ocr/check/', formData).pipe(
      map((response) => normalizeJobEnvelope(response)),
    );
  }

  getOcrStatus(statusUrl: string): Observable<OcrStatusResponse> {
    return this.getOcrStatusResponse(statusUrl).pipe(
      map((response) => normalizeJobEnvelope(response.body as OcrStatusResponse)),
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
    options?: { documentId?: number; docTypeId?: number },
  ): Observable<OcrQueuedResponse | DocumentOcrStatusResponse> {
    const formData = new FormData();
    formData.append('file', file);
    if (typeof options?.documentId === 'number') {
      formData.append('document_id', String(options.documentId));
    }
    if (typeof options?.docTypeId === 'number') {
      formData.append('doc_type_id', String(options.docTypeId));
    }

    return this.http.post<OcrQueuedResponse | DocumentOcrStatusResponse>(
      '/api/document-ocr/check/',
      formData,
    ).pipe(map((response) => normalizeJobEnvelope(response)));
  }

  getDocumentOcrStatus(statusUrl: string): Observable<DocumentOcrStatusResponse> {
    return this.getDocumentOcrStatusResponse(statusUrl).pipe(
      map((response) =>
        normalizeJobEnvelope(response.body as DocumentOcrStatusResponse),
      ),
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
}
