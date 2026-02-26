import { HttpClient, HttpEvent, HttpEventType } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { CustomerApplicationsService } from '@/core/api/api/customer-applications.service';
import { DocumentsService } from '@/core/services/documents.service';
import {
  OcrService,
  type DocumentOcrStatusResponse,
  type OcrQueuedResponse as ServiceOcrQueuedResponse,
} from '@/core/services/ocr.service';

export interface ApplicationCustomer {
  id: number;
  fullName?: string;
  firstName?: string | null;
  lastName?: string | null;
  email?: string | null;
  whatsapp?: string | null;
  telephone?: string | null;
}

export interface ApplicationProduct {
  id: number;
  name: string;
  productType?: string;
  requiredDocuments?: string | null;
  optionalDocuments?: string | null;
  documentsMinValidity?: number | null;
  validationPrompt?: string | null;
}

export interface DocumentTypeInfo {
  id: number;
  name: string;
  aiValidation: boolean;
  hasExpirationDate: boolean;
  hasDocNumber: boolean;
  hasDetails: boolean;
  hasFile: boolean;
  validationRuleAiPositive?: string | null;
  validationRuleAiNegative?: string | null;
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
  aiValidation: boolean;
  aiValidationStatus?: string | null;
  aiValidationResult?: Record<string, unknown> | null;
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
  isCurrentStep?: boolean;
  isOverdue?: boolean;
  isNotificationDateReached?: boolean;
  hasNotes?: boolean;
}

export interface ApplicationTask {
  id: number;
  name: string;
  step: number;
  duration: number;
  durationIsBusinessDays: boolean;
  notifyDaysBefore: number;
  lastStep: boolean;
}

export interface ApplicationDetail {
  id: number;
  customer: ApplicationCustomer;
  product: ApplicationProduct;
  docDate: string;
  dueDate?: string | null;
  addDeadlinesToCalendar?: boolean;
  notifyCustomer?: boolean;
  notifyCustomerChannel?: 'whatsapp' | 'email' | null;
  status: string;
  notes?: string | null;
  documents: ApplicationDocument[];
  workflows: ApplicationWorkflow[];
  isDocumentCollectionCompleted?: boolean;
  isApplicationCompleted?: boolean;
  hasNextTask?: boolean;
  nextTask?: ApplicationTask | null;
  hasInvoice?: boolean;
  invoiceId?: number | null;
  readyForInvoice?: boolean;
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
  text?: string;
  error?: string;
  mrzData?: {
    number?: string;
    expirationDateYyyyMmDd?: string;
  };
  aiWarning?: string;
  b64ResizedImage?: string;
  previewUrl?: string;
}

export type UploadState =
  | { state: 'progress'; progress: number }
  | { state: 'done'; progress: number; document: ApplicationDocument };

@Injectable({
  providedIn: 'root',
})
export class ApplicationsService {
  private http = inject(HttpClient);
  private customerApplicationsService = inject(CustomerApplicationsService);
  private documentsService = inject(DocumentsService);
  private ocrService = inject(OcrService);

  getApplication(applicationId: number): Observable<any> {
    return this.customerApplicationsService.customerApplicationsRetrieve(applicationId, 'body');
  }

  deleteApplication(applicationId: number, deleteInvoices: boolean = false): Observable<any> {
    return this.customerApplicationsService.customerApplicationsDestroy(
      applicationId,
      deleteInvoices,
    );
  }

  advanceWorkflow(applicationId: number): Observable<any> {
    return this.customerApplicationsService.customerApplicationsAdvanceWorkflowCreate(
      applicationId,
      {} as any,
    );
  }

  updateWorkflowStatus(applicationId: number, workflowId: number, status: string): Observable<any> {
    return this.customerApplicationsService.customerApplicationsWorkflowsStatusCreate(
      applicationId,
      workflowId,
      { status },
    );
  }

  updateWorkflowDueDate(
    applicationId: number,
    workflowId: number,
    dueDate: string,
  ): Observable<any> {
    return this.http.post(
      `/api/customer-applications/${applicationId}/workflows/${workflowId}/due-date/`,
      {
        dueDate,
      },
    );
  }

  rollbackWorkflow(applicationId: number, workflowId: number): Observable<any> {
    return this.http.post(
      `/api/customer-applications/${applicationId}/workflows/${workflowId}/rollback/`,
      {},
    );
  }

  reopenApplication(applicationId: number): Observable<any> {
    return this.customerApplicationsService.customerApplicationsReopenCreate(
      applicationId,
      {} as any,
    );
  }

  forceClose(applicationId: number, payload: any): Observable<any> {
    return this.customerApplicationsService.customerApplicationsForceCloseCreate(
      applicationId,
      payload as any,
    );
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
    validateWithAi?: boolean,
  ): Observable<UploadState> {
    // Use DocumentsService wrapper that supports multipart uploads with progress
    return this.documentsService
      .documentsPartialUpdateWithProgress(documentId, {
        docNumber: payload.docNumber ?? undefined,
        expirationDate: payload.expirationDate ?? undefined,
        details: payload.details ?? undefined,
        metadata: payload.metadata ?? undefined,
        file: file ?? undefined,
        validateWithAi,
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

  startDocumentOcr(file: File): Observable<ServiceOcrQueuedResponse | DocumentOcrStatusResponse> {
    return this.ocrService.startDocumentOcr(file);
  }

  getDocumentOcrStatus(statusUrl: string): Observable<DocumentOcrStatusResponse> {
    return this.ocrService.getDocumentOcrStatus(statusUrl);
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
}
