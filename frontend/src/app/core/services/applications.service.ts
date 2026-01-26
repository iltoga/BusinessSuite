import {
  HttpClient,
  HttpEvent,
  HttpEventType,
  HttpHeaders,
  HttpRequest,
} from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface ApplicationCustomer {
  id: number;
  fullName?: string;
  firstName?: string | null;
  lastName?: string | null;
  email?: string | null;
  telephone?: string | null;
}

export interface ApplicationProduct {
  id: number;
  name: string;
  productType?: string;
  requiredDocuments?: string | null;
  optionalDocuments?: string | null;
  documentsMinValidity?: number | null;
}

export interface DocumentTypeInfo {
  id: number;
  name: string;
  hasOcrCheck: boolean;
  hasExpirationDate: boolean;
  hasDocNumber: boolean;
  hasDetails: boolean;
  hasFile: boolean;
}

export interface ApplicationDocument {
  id: number;
  docType: DocumentTypeInfo;
  docNumber?: string | null;
  expirationDate?: string | null;
  fileLink?: string | null;
  details?: string | null;
  completed: boolean;
  metadata?: Record<string, unknown> | null;
  required: boolean;
  ocrCheck: boolean;
  updatedAt?: string | null;
  createdAt?: string | null;
}

export interface ApplicationWorkflow {
  id: number;
  task: {
    id: number;
    name: string;
    step: number;
    duration: number;
    durationIsBusinessDays: boolean;
    notifyDaysBefore: number;
    lastStep: boolean;
  };
  startDate: string;
  dueDate: string;
  completionDate?: string | null;
  status: string;
  notes?: string | null;
}

export interface ApplicationDetail {
  id: number;
  customer: ApplicationCustomer;
  product: ApplicationProduct;
  docDate: string;
  dueDate?: string | null;
  status: string;
  notes?: string | null;
  documents: ApplicationDocument[];
  workflows: ApplicationWorkflow[];
  strField?: string;
}

export interface OcrQueuedResponse {
  jobId: string;
  status: string;
  progress?: number;
  statusUrl?: string;
}

export interface OcrStatusResponse {
  jobId: string;
  status: string;
  progress?: number;
  error?: string;
  mrzData?: {
    number?: string;
    expirationDateYyyyMmDd?: string;
  };
  aiWarning?: string;
  b64ResizedImage?: string;
}

export type UploadState =
  | { state: 'progress'; progress: number }
  | { state: 'done'; progress: number; document: ApplicationDocument };

@Injectable({
  providedIn: 'root',
})
export class ApplicationsService {
  private http = inject(HttpClient);
  private authService = inject(AuthService);
  private apiUrl = '/api/customer-applications/';

  getApplication(applicationId: number): Observable<ApplicationDetail> {
    const headers = this.buildHeaders();
    return this.http.get<ApplicationDetail>(`${this.apiUrl}${applicationId}/`, { headers });
  }

  updateDocument(
    documentId: number,
    payload: {
      docNumber?: string | null;
      expirationDate?: string | null;
      details?: string | null;
      metadata?: Record<string, unknown> | null;
    },
    file?: File | null,
  ): Observable<UploadState> {
    const headers = this.buildHeaders();
    const formData = new FormData();

    if (payload.docNumber) {
      formData.append('doc_number', payload.docNumber);
    }
    if (payload.expirationDate) {
      formData.append('expiration_date', payload.expirationDate);
    }
    if (payload.details) {
      formData.append('details', payload.details);
    }
    if (payload.metadata) {
      formData.append('metadata', JSON.stringify(payload.metadata));
    }
    if (file) {
      formData.append('file', file);
    }

    const request = new HttpRequest('PATCH', `/api/documents/${documentId}/`, formData, {
      headers,
      reportProgress: true,
    });

    return this.http.request<ApplicationDocument>(request).pipe(
      map((event: HttpEvent<ApplicationDocument>) => {
        if (event.type === HttpEventType.UploadProgress) {
          const progress = event.total ? Math.round((event.loaded / event.total) * 100) : 0;
          return { state: 'progress', progress };
        }
        if (event.type === HttpEventType.Response) {
          return { state: 'done', progress: 100, document: event.body as ApplicationDocument };
        }
        return { state: 'progress', progress: 0 };
      }),
    );
  }

  startOcrCheck(file: File, docType: string): Observable<OcrQueuedResponse> {
    const headers = this.buildHeaders();
    const formData = new FormData();
    formData.append('file', file);
    formData.append('doc_type', docType);
    formData.append('use_ai', 'true');
    formData.append('img_preview', 'true');
    formData.append('resize', 'true');
    formData.append('width', '900');

    return this.http.post<OcrQueuedResponse>('/api/ocr/check/', formData, { headers });
  }

  getOcrStatus(statusUrl: string): Observable<OcrStatusResponse> {
    const headers = this.buildHeaders();
    const normalizedUrl = statusUrl.replace(/^https?:\/\/[^/]+/, '');
    return this.http.get<OcrStatusResponse>(normalizedUrl, { headers });
  }

  private buildHeaders(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }
}
