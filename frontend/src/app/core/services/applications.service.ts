/**
 * ApplicationsService — HTTP client and interface definitions for customer
 * application detail, documents, and the OCR upload pipeline.
 *
 * ## Manual interface definitions
 * The interfaces in this file (`ApplicationDocument`, `DocumentTypeInfo`,
 * `ApplicationProduct`, etc.) are **intentionally** hand-written rather than
 * imported from `core/api/` for one of two reasons:
 * 1. The generated type is a flat union or lacks discriminant fields needed
 *    by the UI (e.g. `ApplicationDocument.extraActions`).
 * 2. The interface aggregates fields from multiple generated types into a
 *    single view-model shape consumed by the application detail component.
 *
 * When the generated API client adds an equivalent type that covers all
 * fields, these definitions should be replaced.
 *
 * ## OCR upload pipeline (`uploadDocumentFile`)
 * ```
 * uploadDocumentFile(docId, file)
 *   └─ POST /api/documents/{id}/upload/   (multipart/form-data)
 *      ├─ progress events via HttpClient reportProgress: true
 *      ├─ UploadProgress events → percentage computed from loaded/total
 *      └─ Response event → triggers enqueueDocumentOcr(docId)
 *            └─ POST /api/documents/{id}/enqueue-ocr/
 *               └─ returns { jobId }  →  caller subscribes to SSE stream
 * ```
 *
 * ## Key interfaces
 * | Interface | Purpose |
 * |---|---|
 * | `ApplicationDocument` | Document slot with `docType`, file/OCR state, and extra UI actions |
 * | `DocumentTypeInfo` | Document type metadata driving UI validation rules |
 * | `ApplicationWorkflow` | Single workflow step with deadline and status |
 * | `ApplicationProduct` | Slim product shape for the application detail header |
 * | `ApplicationCustomer` | Slim customer shape for the application detail header |
 */
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
import type { RequestMetadata } from '@/core/utils/request-metadata';

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
  applicationWindowDays?: number | null;
  validationPrompt?: string | null;
}

export interface DocumentTypeInfo {
  id: number;
  name: string;
  autoGeneration?: boolean;
  aiValidation: boolean;
  hasExpirationDate: boolean;
  isStayPermit?: boolean;
  expiringThresholdDays?: number | null;
  hasDocNumber: boolean;
  hasDetails: boolean;
  hasFile: boolean;
  validationRuleAiPositive?: string | null;
  validationRuleAiNegative?: string | null;
  aiStructuredOutput?: string | null;
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
  thumbnailLink?: string | null;
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
  streamUrl?: string;
}

export interface OcrStatusResponse {
  jobId: string;
  status: string;
  progress?: number;
  resultText?: string;
  structuredData?: Record<string, string | null>;
  errorMessage?: string;
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

  updateApplicationPartial(
    applicationId: number,
    payload: Record<string, unknown>,
  ): Observable<any> {
    return this.customerApplicationsService.customerApplicationsPartialUpdate(
      applicationId,
      payload as any,
    );
  }

  updateWorkflowDueDate(
    applicationId: number,
    workflowId: number,
    dueDate: string,
  ): Observable<any> {
    return this.customerApplicationsService.customerApplicationsWorkflowsDueDateCreate(
      applicationId,
      workflowId,
      { dueDate },
    );
  }

  rollbackWorkflow(applicationId: number, workflowId: number): Observable<any> {
    return this.customerApplicationsService.customerApplicationsWorkflowsRollbackCreate(
      applicationId,
      workflowId,
      {} as any,
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
    aiValidationStatusOverride?: '' | 'valid' | 'invalid' | 'error',
    aiValidationResultOverride?: Record<string, unknown> | null,
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
        aiValidationStatusOverride,
        aiValidationResultOverride,
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

  startDocumentOcr(
    file: File,
    options?: { documentId?: number; docTypeId?: number; requestMetadata?: RequestMetadata | null },
  ): Observable<ServiceOcrQueuedResponse | DocumentOcrStatusResponse> {
    return this.ocrService.startDocumentOcr(file, options);
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
