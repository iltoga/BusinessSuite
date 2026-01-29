import { CommonModule, Location } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
  type OnInit,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule } from '@angular/forms';
import { ActivatedRoute, Router, RouterLink } from '@angular/router';

import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationDocument,
  type DocumentAction,
  type OcrStatusResponse,
} from '@/core/services/applications.service';
import { DocumentsService } from '@/core/services/documents.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { DocumentPreviewComponent } from '@/shared/components/document-preview';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardInputDirective } from '@/shared/components/input';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

@Component({
  selector: 'app-application-detail',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    ReactiveFormsModule,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ZardComboboxComponent,
    DocumentPreviewComponent,
    FileUploadComponent,
    ZardIconComponent,
    ZardInputDirective,
    ZardPopoverComponent,
    ZardPopoverDirective,
    AppDatePipe,
  ],
  templateUrl: './application-detail.component.html',
  styleUrls: ['./application-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private router = inject(Router);
  private location = inject(Location);
  private applicationsService = inject(ApplicationsService);
  private documentsService = inject(DocumentsService);
  private toast = inject(GlobalToastService);
  private fb = inject(FormBuilder);
  private destroyRef = inject(DestroyRef);

  readonly application = signal<ApplicationDetail | null>(null);
  readonly isLoading = signal(true);
  readonly isUploadOpen = signal(false);
  readonly selectedDocument = signal<ApplicationDocument | null>(null);
  readonly selectedFile = signal<File | null>(null);
  readonly uploadProgress = signal<number | null>(null);
  readonly isSaving = signal(false);

  readonly ocrPolling = signal(false);
  readonly ocrStatus = signal<string | null>(null);
  readonly ocrPreviewImage = signal<string | null>(null);
  readonly ocrReviewOpen = signal(false);
  readonly ocrReviewData = signal<OcrStatusResponse | null>(null);
  readonly ocrMetadata = signal<Record<string, unknown> | null>(null);
  readonly actionLoading = signal<string | null>(null);
  readonly workflowAction = signal<string | null>(null);

  readonly workflowStatusOptions: ZardComboboxOption[] = [
    { value: 'pending', label: 'Pending' },
    { value: 'processing', label: 'Processing' },
    { value: 'completed', label: 'Completed' },
    { value: 'rejected', label: 'Rejected' },
  ];

  private pollTimer: number | null = null;

  readonly uploadedDocuments = computed(() =>
    (this.application()?.documents ?? []).filter((doc) => doc.completed),
  );
  readonly requiredDocuments = computed(() =>
    (this.application()?.documents ?? []).filter((doc) => doc.required && !doc.completed),
  );
  readonly optionalDocuments = computed(() =>
    (this.application()?.documents ?? []).filter((doc) => !doc.required && !doc.completed),
  );

  readonly sortedWorkflows = computed(() => {
    const workflows = this.application()?.workflows ?? [];
    return [...workflows].sort((a, b) => (a.task?.step ?? 0) - (b.task?.step ?? 0));
  });

  readonly canAdvanceWorkflow = computed(() => {
    const app = this.application();
    if (!app) return false;
    return !!app.isDocumentCollectionCompleted && !!app.hasNextTask && !app.isApplicationCompleted;
  });

  readonly canReopen = computed(() => !!this.application()?.isApplicationCompleted);

  readonly uploadForm = this.fb.group({
    docNumber: [''],
    expirationDate: [''],
    details: [''],
  });

  ngOnInit(): void {
    const id = Number(this.route.snapshot.paramMap.get('id'));
    if (!id) {
      this.toast.error('Invalid application ID');
      this.isLoading.set(false);
      return;
    }
    this.loadApplication(id);

    this.destroyRef.onDestroy(() => {
      if (this.pollTimer) {
        window.clearTimeout(this.pollTimer);
      }
    });
  }

  openUpload(document: ApplicationDocument): void {
    this.selectedDocument.set(document);
    this.selectedFile.set(null);
    this.uploadProgress.set(null);
    this.ocrPreviewImage.set(null);
    this.ocrReviewOpen.set(false);
    this.ocrReviewData.set(null);
    this.ocrMetadata.set(document.metadata ?? null);
    this.uploadForm.reset({
      docNumber: document.docNumber ?? '',
      expirationDate: document.expirationDate ?? '',
      details: document.details ?? '',
    });
    this.isUploadOpen.set(true);
  }

  closeUpload(): void {
    this.isUploadOpen.set(false);
    this.selectedDocument.set(null);
    this.selectedFile.set(null);
    this.uploadProgress.set(null);
    this.ocrPolling.set(false);
    this.ocrStatus.set(null);
  }

  onFileSelected(file: File): void {
    this.selectedFile.set(file);
  }

  onFileCleared(): void {
    this.selectedFile.set(null);
  }

  onSaveDocument(): void {
    const document = this.selectedDocument();
    if (!document) {
      return;
    }

    this.isSaving.set(true);
    this.uploadProgress.set(0);

    const formValue = this.uploadForm.getRawValue();

    this.applicationsService
      .updateDocument(
        document.id,
        {
          docNumber: formValue.docNumber || null,
          expirationDate: formValue.expirationDate || null,
          details: formValue.details || null,
          metadata: this.ocrMetadata(),
        },
        this.selectedFile(),
      )
      .subscribe({
        next: (state) => {
          if (state.state === 'progress') {
            this.uploadProgress.set(state.progress);
          } else {
            this.uploadProgress.set(state.progress);
            this.replaceDocument(state.document);
            this.toast.success('Document updated');
            this.isSaving.set(false);
            this.closeUpload();
          }
        },
        error: () => {
          this.toast.error('Failed to update document');
          this.isSaving.set(false);
        },
      });
  }

  runOcr(): void {
    const document = this.selectedDocument();
    const file = this.selectedFile();
    if (!document || !document.docType?.hasOcrCheck) {
      return;
    }
    if (!file) {
      this.toast.error('Select a file before running OCR');
      return;
    }

    this.ocrPolling.set(true);
    this.ocrStatus.set('Queued');

    this.applicationsService.startOcrCheck(file, document.docType.name).subscribe({
      next: (response) => {
        const statusUrl =
          ('statusUrl' in response && response.statusUrl) ||
          (response as { status_url?: string }).status_url;
        if (statusUrl) {
          this.pollOcrStatus(statusUrl, 0);
        } else {
          this.handleOcrResult(response as OcrStatusResponse);
        }
      },
      error: () => {
        this.toast.error('Failed to start OCR');
        this.ocrPolling.set(false);
      },
    });
  }

  applyOcrData(): void {
    const data = this.ocrReviewData();
    if (!data?.mrzData) {
      this.ocrReviewOpen.set(false);
      return;
    }

    this.uploadForm.patchValue({
      docNumber: data.mrzData.number ?? '',
      expirationDate: data.mrzData.expirationDateYyyyMmDd ?? '',
    });
    this.ocrMetadata.set(data.mrzData ?? {});
    this.ocrReviewOpen.set(false);
  }

  dismissOcrReview(): void {
    this.ocrReviewOpen.set(false);
  }

  executeAction(action: DocumentAction): void {
    const document = this.selectedDocument();
    if (!document) {
      return;
    }

    this.actionLoading.set(action.name);

    this.applicationsService.executeDocumentAction(document.id, action.name).subscribe({
      next: (response) => {
        if (response.success) {
          this.toast.success(response.message ?? 'Action completed successfully');
          if (response.document) {
            this.replaceDocument(response.document);
            // Update selected document with new data
            this.selectedDocument.set(response.document);
            // Update file name in upload component if file was uploaded
            if (response.document.fileLink) {
              this.selectedFile.set(null);
            }
          }
        } else {
          this.toast.error('Action failed');
        }
        this.actionLoading.set(null);
      },
      error: () => {
        this.toast.error('Failed to execute action');
        this.actionLoading.set(null);
      },
    });
  }

  viewDocument(doc: ApplicationDocument): void {
    this.documentsService.downloadDocumentFile(doc.id).subscribe({
      next: (blob) => {
        const url = URL.createObjectURL(blob);
        const popup = window.open(url, '_blank');
        if (!popup) {
          this.toast.error('Popup blocked. Please allow popups for this site.');
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      },
      error: () => {
        if (doc.fileLink) {
          window.open(doc.fileLink, '_blank');
          return;
        }
        this.toast.error('Failed to open document');
      },
    });
  }

  advanceWorkflow(): void {
    const app = this.application();
    if (!app) return;

    this.workflowAction.set('advance');
    this.applicationsService.advanceWorkflow(app.id).subscribe({
      next: () => {
        this.toast.success('Workflow advanced');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: () => {
        this.toast.error('Failed to advance workflow');
        this.workflowAction.set(null);
      },
    });
  }

  updateWorkflowStatus(workflowId: number, status: string | null): void {
    const app = this.application();
    if (!app || !status) return;

    this.workflowAction.set(`status-${workflowId}`);
    this.applicationsService.updateWorkflowStatus(app.id, workflowId, status).subscribe({
      next: () => {
        this.toast.success('Workflow status updated');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: () => {
        this.toast.error('Failed to update workflow status');
        this.workflowAction.set(null);
      },
    });
  }

  reopenApplication(): void {
    const app = this.application();
    if (!app) return;

    this.workflowAction.set('reopen');
    this.applicationsService.reopenApplication(app.id).subscribe({
      next: () => {
        this.toast.success('Application re-opened');
        this.loadApplication(app.id);
        this.workflowAction.set(null);
      },
      error: () => {
        this.toast.error('Failed to re-open application');
        this.workflowAction.set(null);
      },
    });
  }

  getWorkflowStatusVariant(
    status: string,
    isOverdue?: boolean,
  ): 'default' | 'secondary' | 'warning' | 'success' | 'destructive' {
    if (isOverdue) {
      return 'destructive';
    }
    switch (status) {
      case 'completed':
        return 'success';
      case 'processing':
        return 'warning';
      case 'rejected':
        return 'destructive';
      case 'pending':
      default:
        return 'secondary';
    }
  }

  /**
   * Navigate back to the previous view that opened this page.
   * Strategy:
   * 1. If navigation state provides a `from`/`returnUrl`, navigate there
   * 2. Else, if there is a browser history, use Location.back()
   * 3. Fallback to the customer view
   */
  goBack(): void {
    // If the navigation contained a 'from' value in state, use it
    const nav = this.router.getCurrentNavigation();
    const stateFrom =
      (nav && nav.extras && (nav.extras.state as any)?.from) ||
      (history.state && (history.state as any).from);
    if (stateFrom) {
      if (typeof stateFrom === 'string') {
        this.router.navigateByUrl(stateFrom);
      } else {
        this.router.navigate(stateFrom as any[]);
      }
      return;
    }

    // Use browser history if available
    try {
      if (window.history.length > 1) {
        this.location.back();
        return;
      }
    } catch (e) {
      // ignore and fallback
    }

    // Fallback to customer profile
    const customerId = this.application()?.customer.id;
    if (customerId) {
      this.router.navigate(['/customers', customerId]);
    } else {
      this.router.navigate(['/customers']);
    }
  }

  private loadApplication(id: number): void {
    this.isLoading.set(true);
    this.applicationsService.getApplication(id).subscribe({
      next: (data) => {
        this.application.set(data);
        this.isLoading.set(false);
      },
      error: () => {
        this.toast.error('Failed to load application');
        this.isLoading.set(false);
      },
    });
  }

  private pollOcrStatus(statusUrl: string, attempt: number): void {
    const maxAttempts = 90;
    const intervalMs = 2000;

    if (attempt >= maxAttempts) {
      this.toast.error('OCR processing timed out');
      this.ocrPolling.set(false);
      return;
    }

    this.pollTimer = window.setTimeout(() => {
      this.applicationsService.getOcrStatus(statusUrl).subscribe({
        next: (status) => {
          if (status.status === 'completed') {
            this.handleOcrResult(status);
            return;
          }
          if (status.status === 'failed') {
            this.toast.error(status.error ?? 'OCR failed');
            this.ocrPolling.set(false);
            return;
          }
          if (typeof status.progress === 'number') {
            this.ocrStatus.set(`Processing ${status.progress}%`);
          } else {
            this.ocrStatus.set('Processing');
          }
          this.pollOcrStatus(statusUrl, attempt + 1);
        },
        error: () => {
          this.toast.error('Failed to check OCR status');
          this.ocrPolling.set(false);
        },
      });
    }, intervalMs);
  }

  private handleOcrResult(status: OcrStatusResponse): void {
    this.ocrPolling.set(false);
    this.ocrStatus.set('Completed');
    this.ocrReviewData.set(status);
    if (status.b64ResizedImage) {
      this.ocrPreviewImage.set(`data:image/jpeg;base64,${status.b64ResizedImage}`);
    }
    this.ocrReviewOpen.set(true);
  }

  private replaceDocument(updated: ApplicationDocument): void {
    const application = this.application();
    if (!application) {
      return;
    }
    const documents = application.documents.map((doc) =>
      doc.id === updated.id ? { ...doc, ...updated } : doc,
    );
    this.application.set({ ...application, documents });
  }
}
