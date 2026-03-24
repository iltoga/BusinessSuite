import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  DestroyRef,
  inject,
  input,
  output,
  signal,
  ViewChild,
} from '@angular/core';
import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';

import { DocumentsService } from '@/core/services/documents.service';
import { ZardButtonComponent } from '@/shared/components/button';
import type {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardIconComponent } from '@/shared/components/icon';
import { ImageMagnifierComponent } from '@/shared/components/image-magnifier';
import { ZardDialogRef } from '@/shared/components/dialog';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';
import { DocumentViewerOverlayService } from '@/shared/services/document-viewer-overlay.service';
import { inferPreviewTypeFromUrl } from '@/shared/utils/document-preview-source';
import { sanitizeResourceUrl } from '@/shared/utils/resource-url-sanitizer';

@Component({
  selector: 'app-document-preview',
  standalone: true,
  imports: [
    CommonModule,
    ZardButtonComponent,
    ZardIconComponent,
    ImageMagnifierComponent,
    ZardPopoverComponent,
    ZardPopoverDirective,
  ],
  templateUrl: './document-preview.component.html',
  styleUrls: ['./document-preview.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DocumentPreviewComponent {
  private documentsService = inject(DocumentsService);
  private destroyRef = inject(DestroyRef);
  private sanitizer = inject(DomSanitizer);
  private dialogRef = inject(ZardDialogRef, { optional: true });
  private viewerService = inject(DocumentViewerOverlayService);

  documentId = input.required<number>();
  fileLink = input<string | null | undefined>(null);
  thumbnailLink = input<string | null | undefined>(null);
  label = input<string>('Preview');
  zType = input<ZardButtonTypeVariants>('outline');
  zSize = input<ZardButtonSizeVariants>('sm');
  previewSize = input<'sm' | 'md' | 'lg'>('sm');
  // If true, request the popover to be centered in the viewport instead of anchored to the trigger
  centerInViewport = input<boolean>(false);

  viewFull = output<void>();

  isLoading = signal(false);
  previewBlob = signal<Blob | null>(null);
  previewUrl = signal<string | null>(null);
  sanitizedPreview = signal<SafeResourceUrl | null>(null);
  previewMime = signal<string | null>(null);

  @ViewChild('popover', { read: ZardPopoverDirective, static: false })
  protected popover?: ZardPopoverDirective;

  protected readonly fileName = computed(() => this.extractFileName(this.fileLink()));
  protected readonly resolvedFileType = computed<'image' | 'pdf' | 'unknown'>(() => {
    const fromMime = this.inferTypeFromMime(this.previewMime());
    if (fromMime !== 'unknown') {
      return fromMime;
    }
    return inferPreviewTypeFromUrl(this.fileLink());
  });
  protected readonly isPdf = computed(() => this.resolvedFileType() === 'pdf');

  protected readonly isImage = computed(() => this.resolvedFileType() === 'image');

  protected readonly isPdfImage = computed(() => {
    const mime = this.previewMime();
    if (mime?.startsWith('image/')) {
      return true;
    }
    const url = this.previewUrl();
    if (!url) {
      return false;
    }
    const normalized = url.toLowerCase();
    if (normalized.startsWith('data:image')) {
      return true;
    }
    return /\.(png|jpe?g|webp|gif|bmp|avif)(?:$|[?#])/i.test(normalized);
  });

  protected readonly popoverClasses = computed(() => {
    // Reduce the popover width to 2/3 of the previous value and keep responsive variants.
    // These sizes are chosen so the preview is not overly wide and fit common screen sizes.
    switch (this.previewSize()) {
      case 'lg':
        // approx 2/3 of previous lg sizes
        return 'p-3 w-[36rem] sm:w-[45rem]';
      case 'md':
        // approx 2/3 of previous md sizes
        return 'p-3 w-[32rem] sm:w-[36rem]';
      case 'sm':
      default:
        // approx 2/3 of previous sm sizes
        return 'p-2 w-[24rem] sm:w-[28rem]';
    }
  });

  protected readonly previewFrameClasses = computed(() => {
    // Use heights approximating A4 aspect ratio (height ≈ width * 1.414) for each size.
    switch (this.previewSize()) {
      case 'lg':
        // width ~45rem => height ~64rem (clamped to nicer rem)
        return 'w-full h-[64rem]';
      case 'md':
        // width ~36rem => height ~51rem
        return 'w-full h-[51rem]';
      case 'sm':
      default:
        // width ~28rem => height ~40rem
        return 'w-full h-[40rem]';
    }
  });

  protected readonly previewImageClasses = computed(() => {
    // Match the image max-height to the frame heights to maintain A4-like proportions
    switch (this.previewSize()) {
      case 'lg':
        return 'max-h-[64rem] w-full object-contain';
      case 'md':
        return 'max-h-[51rem] w-full object-contain';
      case 'sm':
      default:
        return 'max-h-[40rem] w-full object-contain';
    }
  });

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.cleanup();
      this.viewerService.closeCurrent();
    });
  }

  protected onPopoverToggle(visible: boolean): void {
    if (visible && !this.previewUrl() && !this.isLoading()) {
      this.loadPreview();
    }
    // We don't cleanup immediately on hide to avoid flickering if reopened,
    // but we could if memory is a concern. The destroyRef handles cleanup.
  }

  protected onViewFull(): void {
    // Hide popover immediately to avoid the small preview lingering under the viewer
    this.popover?.hide();

    // For PDFs, open the inline lazy-loaded viewer here and do NOT emit to parent
    if (this.isPdf()) {
      if (this.previewBlob()) {
        this.openViewer();
      } else if (!this.isLoading()) {
        this.loadPreviewAndOpen();
      }
      return;
    }

    // For images, open the inline image viewer overlay
    if (this.isImage()) {
      if (this.previewBlob() || this.previewUrl()) {
        this.openImageViewer();
      } else if (!this.isLoading()) {
        this.loadPreviewAndOpenImage();
      }
      return;
    }

    // Other file types: fallback to previous behavior and inform the parent
    this.viewFull.emit();
  }

  private loadPreviewAndOpen(): void {
    this.isLoading.set(true);
    this.documentsService.downloadDocumentFile(this.documentId()).subscribe({
      next: async (blob) => {
        this.cleanup();
        this.previewBlob.set(blob);
        this.previewMime.set(blob.type ?? null);

        // Try generate a thumbnail for PDF for popover preview. Don't block opening the viewer.
        if (this.isPdf()) {
          const thumb = await this.generatePdfThumbnail(blob);
          if (thumb) {
            if (!this.setPreviewResourceUrl(thumb)) {
              this.previewUrl.set(null);
            }
          } else {
            const url = URL.createObjectURL(blob);
            if (!this.setPreviewResourceUrl(url)) {
              URL.revokeObjectURL(url);
              this.previewUrl.set(null);
            }
          }
        } else {
          const url = URL.createObjectURL(blob);
          if (!this.setPreviewResourceUrl(url)) {
            URL.revokeObjectURL(url);
            this.previewUrl.set(null);
          }
        }

        this.isLoading.set(false);
        this.openViewer();
      },
      error: () => {
        this.isLoading.set(false);
        this.previewUrl.set(null);
        this.previewBlob.set(null);
        this.previewMime.set(null);
      },
    });
  }

  private loadPreview(): void {
    this.isLoading.set(true);
    this.cleanup();

    if (this.tryUseThumbnailLink()) {
      this.isLoading.set(false);
      return;
    }

    this.documentsService.downloadDocumentFile(this.documentId()).subscribe({
      next: async (blob) => {
        this.cleanup();
        this.previewBlob.set(blob);
        this.previewMime.set(blob.type ?? null);

        // Try to generate an inline image thumbnail for PDFs for a better preview
        if (this.isPdf()) {
          const thumb = await this.generatePdfThumbnail(blob);
          if (thumb) {
            this.setPreviewResourceUrl(thumb);
            this.isLoading.set(false);
            return;
          }
        }

        const url = URL.createObjectURL(blob);
        if (!this.setPreviewResourceUrl(url)) {
          URL.revokeObjectURL(url);
        }
        this.isLoading.set(false);
      },
      error: () => {
        this.isLoading.set(false);
        this.previewUrl.set(null);
        this.previewBlob.set(null);
        this.previewMime.set(null);
      },
    });
  }

  private tryUseThumbnailLink(): boolean {
    // For PDF originals, prefer fetching the source PDF so full preview can open
    // the real document instead of a static image thumbnail.
    if (inferPreviewTypeFromUrl(this.fileLink()) === 'pdf') {
      return false;
    }

    const thumbnail = this.thumbnailLink();
    if (!thumbnail) {
      return false;
    }
    if (this.isLikelyExpiringStorageUrl(thumbnail)) {
      return false;
    }

    const imageMime = this.guessImageMimeFromUrl(thumbnail);
    if (!imageMime) {
      return false;
    }

    if (!this.setPreviewResourceUrl(thumbnail)) {
      return false;
    }

    this.previewMime.set(imageMime);
    this.previewBlob.set(null);
    return true;
  }

  private openViewer(): void {
    let passedSrc: any = this.previewBlob();
    // Prefer passing the Blob directly to ngx-extended-pdf-viewer when available
    if (this.previewBlob() instanceof Blob) {
      passedSrc = this.previewBlob() as Blob;
    }

    this.viewerService.openPdfViewer(passedSrc, { dialogRef: this.dialogRef ?? undefined });
  }

  private openImageViewer(): void {
    // Determine the source: prefer blob, fall back to URL
    const passedSrc: any = this.previewBlob() ?? this.previewUrl();
    this.viewerService.openImageViewer(passedSrc, { dialogRef: this.dialogRef ?? undefined });
  }

  private loadPreviewAndOpenImage(): void {
    this.isLoading.set(true);
    this.documentsService.downloadDocumentFile(this.documentId()).subscribe({
      next: (blob) => {
        this.cleanup();
        this.previewBlob.set(blob);
        this.previewMime.set(blob.type ?? null);

        const url = URL.createObjectURL(blob);
        if (!this.setPreviewResourceUrl(url)) {
          URL.revokeObjectURL(url);
          this.previewUrl.set(null);
        }

        this.isLoading.set(false);
        this.openImageViewer();
      },
      error: () => {
        this.isLoading.set(false);
        this.previewUrl.set(null);
        this.previewBlob.set(null);
        this.previewMime.set(null);
      },
    });
  }

  private cleanup(): void {
    const url = this.previewUrl();
    if (url && url.startsWith('blob:')) {
      URL.revokeObjectURL(url);
    }
    this.previewUrl.set(null);
    this.sanitizedPreview.set(null);
    this.previewMime.set(null);
    // keep previewBlob available for full-view until destroyed explicitly
  }

  private setPreviewResourceUrl(url: string): boolean {
    const safeUrl = sanitizeResourceUrl(url, this.sanitizer);
    if (!safeUrl) {
      this.sanitizedPreview.set(null);
      this.previewUrl.set(null);
      return false;
    }
    this.previewUrl.set(url);
    this.sanitizedPreview.set(safeUrl);
    return true;
  }

  private guessImageMimeFromUrl(url: string): string | null {
    const normalized = (url || '').toLowerCase();
    if (normalized.startsWith('data:image')) {
      return 'image/*';
    }
    if (normalized.includes('.png')) {
      return 'image/png';
    }
    if (normalized.includes('.jpg') || normalized.includes('.jpeg')) {
      return 'image/jpeg';
    }
    if (normalized.includes('.webp')) {
      return 'image/webp';
    }
    if (normalized.includes('.gif')) {
      return 'image/gif';
    }
    if (normalized.includes('.bmp')) {
      return 'image/bmp';
    }
    if (normalized.includes('.avif')) {
      return 'image/avif';
    }
    return null;
  }

  private inferTypeFromMime(mime: string | null): 'image' | 'pdf' | 'unknown' {
    const normalized = (mime || '').toLowerCase();
    if (normalized === 'application/pdf') {
      return 'pdf';
    }
    if (normalized.startsWith('image/')) {
      return 'image';
    }
    return 'unknown';
  }

  private extractFileName(url: string | null | undefined): string {
    const value = (url || '').trim();
    if (!value) {
      return 'Document';
    }

    try {
      const parsed = new URL(value);
      const segment = parsed.pathname.split('/').filter(Boolean).pop() || '';
      if (segment) {
        return this.decodeSafely(segment);
      }
    } catch {
      // Fall back to simple parsing below for non-standard URL values.
    }

    const fallback = value.split('?')[0]?.split('#')[0]?.split('/').pop() || '';
    return fallback ? this.decodeSafely(fallback) : 'Document';
  }

  private decodeSafely(value: string): string {
    try {
      return decodeURIComponent(value);
    } catch {
      return value;
    }
  }

  private isLikelyExpiringStorageUrl(url: string): boolean {
    const trimmed = (url || '').trim();
    if (!trimmed || trimmed.startsWith('blob:') || trimmed.startsWith('data:')) {
      return false;
    }

    const lower = trimmed.toLowerCase();
    if (
      lower.includes('x-amz-') ||
      lower.includes('signature=') ||
      lower.includes('expires=') ||
      lower.includes('token=')
    ) {
      return true;
    }

    try {
      const parsed = new URL(trimmed);
      return parsed.searchParams.size > 0;
    } catch {
      return false;
    }
  }

  private async generatePdfThumbnail(blob: Blob): Promise<string | null> {
    try {
      // Lazy-load pdfjs to avoid bundling it in the main chunk
      // Use a generic import to avoid TypeScript module resolution issues and avoid importing the worker entry
      // which can cause problems with Vite's optimizeDeps. Try a local worker first (/assets/pdf.worker.min.js)
      // and fall back to CDN if it's not present.
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      const pdfjs = await import('pdfjs-dist');

      const PDFJS_VERSION = '5.4.530';
      // Determine worker src: prefer local asset then CDN
      let workerSrc = `/assets/pdf.worker.min.js`;
      try {
        const res = await fetch(workerSrc, { method: 'HEAD' });
        const contentType = res.headers.get('content-type') || '';
        // If the asset endpoint returns HTML (index.html), fall back to CDN
        if (!res.ok || contentType.includes('text/html')) {
          workerSrc = `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.js`;
        }
      } catch (e) {
        workerSrc = `https://unpkg.com/pdfjs-dist@${PDFJS_VERSION}/build/pdf.worker.min.js`;
      }

      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      pdfjs.GlobalWorkerOptions = pdfjs.GlobalWorkerOptions || {};
      // eslint-disable-next-line @typescript-eslint/ban-ts-comment
      // @ts-ignore
      pdfjs.GlobalWorkerOptions.workerSrc = workerSrc;

      const arrayBuffer = await blob.arrayBuffer();
      const doc = await (pdfjs as any).getDocument({ data: arrayBuffer }).promise;
      const page = await doc.getPage(1);
      const viewport = page.getViewport({ scale: 1.0 });

      const maxWidth = 800;
      const maxHeight = 600;
      const scale = Math.min(maxWidth / viewport.width, maxHeight / viewport.height, 1);
      const scaledViewport = page.getViewport({ scale });

      const canvas = document.createElement('canvas');
      canvas.width = Math.round(scaledViewport.width);
      canvas.height = Math.round(scaledViewport.height);
      const ctx = canvas.getContext('2d');
      if (!ctx) return null;

      await page.render({ canvasContext: ctx as any, viewport: scaledViewport }).promise;
      return canvas.toDataURL('image/png');
    } catch (e) {
      // If pdfjs fails for any reason, silently fall back to using the blob URL
      return null;
    }
  }
}
