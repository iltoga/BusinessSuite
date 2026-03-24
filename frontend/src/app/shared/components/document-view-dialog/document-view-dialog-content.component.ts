import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  inject,
  type OnInit,
  signal,
} from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';

import type { ApplicationDocument } from '@/core/services/applications.service';
import { DocumentsService } from '@/core/services/documents.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { Z_MODAL_DATA } from '@/shared/components/dialog';
import { ZardIconComponent } from '@/shared/components/icon';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { inferPreviewTypeFromUrl } from '@/shared/utils/document-preview-source';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { sanitizeResourceUrl } from '@/shared/utils/resource-url-sanitizer';

export interface DocumentViewDialogData {
  document: ApplicationDocument;
}

@Component({
  selector: 'app-document-view-dialog-content',
  standalone: true,
  imports: [
    CommonModule,
    ZardButtonComponent,
    ZardIconComponent,
    ImageMagnifierComponent,
    AppDatePipe,
  ],
  templateUrl: './document-view-dialog-content.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentViewDialogContentComponent implements OnInit {
  readonly data = inject<DocumentViewDialogData>(Z_MODAL_DATA);
  private destroyRef = inject(DestroyRef);
  private documentsService = inject(DocumentsService);
  private toast = inject(GlobalToastService);
  private sanitizer = inject(DomSanitizer);

  readonly isLoadingPreview = signal(false);
  readonly isLoadingFullFile = signal(false);
  readonly previewUrl = signal<string | null>(null);
  readonly sanitizedPreviewUrl = signal<SafeResourceUrl | null>(null);
  readonly previewType = signal<'image' | 'pdf' | 'unknown'>('unknown');

  get doc(): ApplicationDocument {
    return this.data.document;
  }

  get hasFile(): boolean {
    return !!this.doc.fileLink;
  }

  get hasDocNumber(): boolean {
    return !!this.doc.docNumber;
  }

  get hasExpirationDate(): boolean {
    return !!this.doc.expirationDate;
  }

  get hasDetails(): boolean {
    return !!this.doc.details;
  }

  get hasTextFields(): boolean {
    return this.hasDocNumber || this.hasExpirationDate || this.hasDetails;
  }

  get isImage(): boolean {
    return this.previewType() === 'image';
  }

  get isPdf(): boolean {
    return this.previewType() === 'pdf';
  }

  constructor() {
    this.destroyRef.onDestroy(() => this.revokePreview());
  }

  ngOnInit(): void {
    if (this.hasFile) {
      this.loadPreview();
    }
  }

  viewFullFile(): void {
    this.isLoadingFullFile.set(true);
    this.documentsService.downloadDocumentFile(this.doc.id).subscribe({
      next: (blob) => {
        this.isLoadingFullFile.set(false);
        const url = URL.createObjectURL(blob);
        const popup = window.open(url, '_blank');
        if (!popup) {
          this.toast.error('Popup blocked. Please allow popups for this site.');
        }
        window.setTimeout(() => URL.revokeObjectURL(url), 60000);
      },
      error: (error) => {
        this.isLoadingFullFile.set(false);
        if (this.doc.fileLink) {
          window.open(this.doc.fileLink, '_blank');
          return;
        }
        this.toast.error(extractServerErrorMessage(error) || 'Failed to open document');
      },
    });
  }

  private loadPreview(): void {
    this.isLoadingPreview.set(true);
    this.documentsService.downloadDocumentFile(this.doc.id).subscribe({
      next: (blob) => {
        this.revokePreview();
        const mime = (blob.type ?? '').toLowerCase();
        if (mime.startsWith('image/')) {
          this.previewType.set('image');
        } else if (mime === 'application/pdf') {
          this.previewType.set('pdf');
        } else {
          this.previewType.set(inferPreviewTypeFromUrl(this.doc.fileLink));
        }
        const url = URL.createObjectURL(blob);
        const safe = sanitizeResourceUrl(url, this.sanitizer);
        if (safe) {
          this.previewUrl.set(url);
          this.sanitizedPreviewUrl.set(safe);
        } else {
          URL.revokeObjectURL(url);
        }
        this.isLoadingPreview.set(false);
      },
      error: () => {
        this.isLoadingPreview.set(false);
        this.previewType.set(inferPreviewTypeFromUrl(this.doc.fileLink));
      },
    });
  }

  private revokePreview(): void {
    const url = this.previewUrl();
    if (url?.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
    this.previewUrl.set(null);
    this.sanitizedPreviewUrl.set(null);
  }
}
