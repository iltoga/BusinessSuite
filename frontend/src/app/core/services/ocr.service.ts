import { HttpClient, HttpHeaders, HttpResponse } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface OcrQueuedResponse {
  jobId: string;
  status: string;
  progress?: number;
  statusUrl?: string;
  streamUrl?: string;
}

export interface OcrStatusResponse {
  jobId: string;
  status: string;
  progress?: number;
  error?: string;
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
  text?: string;
  structuredData?: Record<string, string | null>;
  structured_data?: Record<string, string | null>;
  error?: string;
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
  private authService = inject(AuthService);

  startPassportOcr(
    file: File,
    options: PassportOcrOptions,
  ): Observable<OcrQueuedResponse | OcrStatusResponse> {
    const headers = this.buildHeaders();
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

    return this.http.post<OcrQueuedResponse | OcrStatusResponse>('/api/ocr/check/', formData, {
      headers,
    });
  }

  getOcrStatus(statusUrl: string): Observable<OcrStatusResponse> {
    return this.getOcrStatusResponse(statusUrl).pipe(
      map((response) => response.body as OcrStatusResponse),
    );
  }

  getOcrStatusResponse(statusUrl: string): Observable<HttpResponse<OcrStatusResponse>> {
    const headers = this.buildHeaders();
    const normalizedUrl = statusUrl.replace(/^https?:\/\/[^/]+/, '');
    return this.http.get<OcrStatusResponse>(normalizedUrl, {
      headers,
      observe: 'response',
    });
  }

  startDocumentOcr(
    file: File,
    options?: { documentId?: number; docTypeId?: number },
  ): Observable<OcrQueuedResponse | DocumentOcrStatusResponse> {
    const headers = this.buildHeaders();
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
      { headers },
    );
  }

  getDocumentOcrStatus(statusUrl: string): Observable<DocumentOcrStatusResponse> {
    return this.getDocumentOcrStatusResponse(statusUrl).pipe(
      map((response) => response.body as DocumentOcrStatusResponse),
    );
  }

  getDocumentOcrStatusResponse(
    statusUrl: string,
  ): Observable<HttpResponse<DocumentOcrStatusResponse>> {
    const headers = this.buildHeaders();
    const normalizedUrl = statusUrl.replace(/^https?:\/\/[^/]+/, '');
    return this.http.get<DocumentOcrStatusResponse>(normalizedUrl, {
      headers,
      observe: 'response',
    });
  }

  private buildHeaders(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }
}
