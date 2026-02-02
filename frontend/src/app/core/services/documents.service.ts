import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface DocumentPartialUpdatePayload {
  docNumber?: string | null;
  expirationDate?: string | null;
  details?: string | null;
  metadata?: Record<string, unknown> | null;
  file?: File | null;
}

@Injectable({
  providedIn: 'root',
})
export class DocumentsService {
  private http = inject(HttpClient);
  private auth = inject(AuthService);

  documentsPartialUpdateWithProgress(
    documentId: number,
    payload: DocumentPartialUpdatePayload,
  ): Observable<HttpEvent<any>> {
    const url = `/api/documents/${documentId}/`;
    const form = new FormData();

    if (payload.docNumber !== undefined && payload.docNumber !== null) {
      form.append('doc_number', String(payload.docNumber));
    }
    if (payload.expirationDate !== undefined && payload.expirationDate !== null) {
      form.append('expiration_date', String(payload.expirationDate));
    }
    if (payload.details !== undefined && payload.details !== null) {
      form.append('details', String(payload.details));
    }
    if (payload.metadata !== undefined && payload.metadata !== null) {
      try {
        form.append('metadata', JSON.stringify(payload.metadata));
      } catch (e) {
        // if metadata cannot be serialized, skip it
      }
    }
    if (payload.file) {
      form.append('file', payload.file);
    }

    const token = this.auth.getToken();
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    // Use low-level request so we can return HttpEvent for progress
    return this.http.request('patch', url, {
      body: form,
      headers,
      reportProgress: true,
      observe: 'events',
    }) as Observable<HttpEvent<any>>;
  }

  downloadDocumentFile(documentId: number): Observable<Blob> {
    const url = `/api/documents/${documentId}/download/`;
    const token = this.auth.getToken();
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    return this.http.get(url, {
      headers,
      responseType: 'blob',
    });
  }

  mergePdf(documentIds: number[]): Observable<Blob> {
    const url = '/api/documents/merge-pdf/';
    const token = this.auth.getToken();
    const headers: Record<string, string> = token ? { Authorization: `Bearer ${token}` } : {};

    return this.http.post(
      url,
      { document_ids: documentIds },
      {
        headers,
        responseType: 'blob',
      },
    );
  }
}
