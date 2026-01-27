import { HttpClient, HttpEvent, HttpEventType, HttpHeaders } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { AuthService } from '@/core/services/auth.service';
import { DocumentsService } from '@/core/services/documents.service';
import { OcrService } from '@/core/services/ocr.service';

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

export interface DocumentAction {
  name: string;
  label: string;
  icon: string;
  cssClass: string;
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
  updatedByUsername?: string | null;
  createdByUsername?: string | null;
  extraActions?: DocumentAction[];
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
  private customerApplicationsService = inject(CustomerApplicationsService);
  private documentsService = inject(DocumentsService);
  private ocrService = inject(OcrService);

  private apiUrl = '/api/customer-applications/';

  getApplication(applicationId: number): Observable<any> {
    return this.customerApplicationsService.customerApplicationsRetrieve(applicationId, 'body');
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
    // Use DocumentsService wrapper that supports multipart uploads with progress
    return this.documentsService
      .documentsPartialUpdateWithProgress(documentId, {
        docNumber: payload.docNumber ?? undefined,
        expirationDate: payload.expirationDate ?? undefined,
        details: payload.details ?? undefined,
        metadata: payload.metadata ?? undefined,
        file: file ?? undefined,
      })
      .pipe(
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

  startOcrCheck(file: File, docType: string): Observable<any> {
    // Delegate to OcrService which handles headers and form-data building
    return this.ocrService.startPassportOcr(file, { useAi: true, previewWidth: 900 });
  }

  getOcrStatus(statusUrl: string): Observable<OcrStatusResponse> {
    return this.ocrService.getOcrStatus(statusUrl);
  }

  executeDocumentAction(
    documentId: number,
    actionName: string,
  ): Observable<{ success: boolean; message?: string; document?: ApplicationDocument }> {
    return this.http.post<{ success: boolean; message?: string; document?: ApplicationDocument }>(
      `/api/documents/${documentId}/actions/${actionName}/`,
      {},
    );
  }

  private buildHeaders(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }
}
