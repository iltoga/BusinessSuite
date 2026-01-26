import { CommonModule } from '@angular/common';
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
import { ActivatedRoute, RouterLink } from '@angular/router';

import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationDocument,
  type OcrStatusResponse,
} from '@/core/services/applications.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { FileUploadComponent } from '@/shared/components/file-upload';
import { ZardInputDirective } from '@/shared/components/input';
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
    FileUploadComponent,
    ZardInputDirective,
    AppDatePipe,
  ],
  templateUrl: './application-detail.component.html',
  styleUrls: ['./application-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationDetailComponent implements OnInit {
  private route = inject(ActivatedRoute);
  private applicationsService = inject(ApplicationsService);
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
        if (response.statusUrl) {
          this.pollOcrStatus(response.statusUrl, 0);
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
