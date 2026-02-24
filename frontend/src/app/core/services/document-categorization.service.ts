import { HttpClient } from '@angular/common/http';
import { inject, Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface CategorizationStartResponse {
  jobId: string;
  totalFiles: number;
  status: string;
}

export interface CategorizationFileResult {
  itemId: string;
  filename: string;
  status: string;
  documentType: string | null;
  documentTypeId: number | null;
  documentId: number | null;
  confidence: number;
  reasoning: string;
  error: string | null;
}

export interface CategorizationSseEvent {
  type: string;
  data: {
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
}

@Injectable({
  providedIn: 'root',
})
export class DocumentCategorizationService {
  private readonly http = inject(HttpClient);
  private readonly authService = inject(AuthService);
  private readonly zone = inject(NgZone);

  /**
   * Upload files and start AI categorization.
   */
  uploadAndCategorize(
    applicationId: number,
    files: File[],
    model?: string,
    providerOrder?: string[],
  ): Observable<CategorizationStartResponse> {
    const formData = new FormData();
    files.forEach((file) => formData.append('files', file));
    if (model) formData.append('model', model);
    if (providerOrder) formData.append('providerOrder', providerOrder.join(','));

    return this.http.post<CategorizationStartResponse>(
      `/api/customer-applications/${applicationId}/categorize-documents/`,
      formData,
    );
  }

  /**
   * Connect to the SSE stream for categorization progress.
   * Returns events with type and data parsed from SSE event/data lines.
   */
  watchCategorizationJob(jobId: string): Observable<CategorizationSseEvent> {
    return new Observable<CategorizationSseEvent>((subscriber) => {
      const controller = new AbortController();

      const streamSse = async () => {
        try {
          const headers = new Headers({ Accept: 'text/event-stream' });
          const token =
            this.authService.getToken() ?? (this.authService.isMockEnabled() ? 'mock-token' : null);
          if (token) {
            headers.set('Authorization', `Bearer ${token}`);
          }

          const response = await fetch(`/api/document-categorization/stream/${jobId}/`, {
            method: 'GET',
            headers,
            credentials: 'include',
            cache: 'no-store',
            signal: controller.signal,
          });

          if (!response.ok) {
            throw new Error(`SSE request failed (${response.status})`);
          }
          if (!response.body) {
            throw new Error('SSE stream body is unavailable');
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            buffer = buffer.replace(/\r\n/g, '\n');

            let frameBoundary = buffer.indexOf('\n\n');
            while (frameBoundary !== -1) {
              const frame = buffer.slice(0, frameBoundary);
              buffer = buffer.slice(frameBoundary + 2);

              // Parse event type and data
              const lines = frame.split('\n');
              let eventType = 'message';
              let eventData = '';

              for (const line of lines) {
                if (line.startsWith('event: ')) {
                  eventType = line.substring(7).trim();
                } else if (line.startsWith('data: ')) {
                  eventData = line.substring(6);
                } else if (line.startsWith(':')) {
                  // Comment (keep-alive), skip
                  continue;
                }
              }

              if (eventData) {
                try {
                  const data = JSON.parse(eventData);
                  this.zone.run(() => subscriber.next({ type: eventType, data }));
                } catch {
                  // Non-JSON data, skip
                }
              }

              frameBoundary = buffer.indexOf('\n\n');
            }
          }

          this.zone.run(() => subscriber.complete());
        } catch (error) {
          if (controller.signal.aborted) return;
          this.zone.run(() => subscriber.error(error));
        }
      };

      void streamSse();
      return () => controller.abort();
    });
  }

  /**
   * Apply confirmed categorization results.
   */
  applyResults(
    jobId: string,
    mappings: CategorizationApplyMapping[],
  ): Observable<CategorizationApplyResponse> {
    return this.http.post<CategorizationApplyResponse>(
      `/api/document-categorization/${jobId}/apply/`,
      { mappings },
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
