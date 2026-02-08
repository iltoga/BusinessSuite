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
  ViewContainerRef,
} from '@angular/core';

import { DomSanitizer, type SafeResourceUrl } from '@angular/platform-browser';

import { DocumentsService } from '@/core/services/documents.service';
import { ZardButtonComponent } from '@/shared/components/button';
import type {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardPopoverComponent, ZardPopoverDirective } from '@/shared/components/popover';

@Component({
  selector: 'app-document-preview',
  standalone: true,
  imports: [
    CommonModule,
    ZardButtonComponent,
    ZardIconComponent,
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

  documentId = input.required<number>();
  fileLink = input<string | null | undefined>(null);
  label = input<string>('Preview');
  zType = input<ZardButtonTypeVariants>('outline');
  zSize = input<ZardButtonSizeVariants>('sm');
  previewSize = input<'sm' | 'md' | 'lg'>('sm');

  viewFull = output<void>();

  isLoading = signal(false);
  previewBlob = signal<Blob | null>(null);
  previewUrl = signal<string | null>(null);
  sanitizedPreview = signal<SafeResourceUrl | null>(null);
  previewMime = signal<string | null>(null);

  @ViewChild('overlayContainer', { read: ViewContainerRef, static: false })
  protected overlayContainer?: ViewContainerRef;

  @ViewChild('popover', { read: ZardPopoverDirective, static: false })
  protected popover?: ZardPopoverDirective;

  private viewerCompRef: any | null = null;
  private viewerUrl: string | null = null;

  protected readonly fileName = computed(() => this.fileLink()?.split('/').pop() || 'Document');
  protected readonly isPdf = computed(() => {
    const link = this.fileLink()?.toLowerCase() || '';
    const mime = this.previewMime();
    return link.endsWith('.pdf') || mime === 'application/pdf';
  });

  protected readonly isImage = computed(() => {
    const link = this.fileLink()?.toLowerCase() || '';
    const mime = this.previewMime();
    if (mime?.startsWith('image/')) {
      return true;
    }
    return /\.(png|jpe?g)$/i.test(link);
  });

  protected readonly isPdfImage = computed(() => {
    const url = this.previewUrl();
    return !!url && url.startsWith('data:image');
  });

  protected readonly popoverClasses = computed(() => {
    switch (this.previewSize()) {
      case 'lg':
        return 'p-3 w-[28rem] sm:w-[34rem]';
      case 'md':
        return 'p-3 w-96 sm:w-[28rem]';
      case 'sm':
      default:
        return 'p-2 w-72 sm:w-80';
    }
  });

  protected readonly previewFrameClasses = computed(() => {
    switch (this.previewSize()) {
      case 'lg':
        return 'w-full h-[26rem]';
      case 'md':
        return 'w-full h-80';
      case 'sm':
      default:
        return 'w-full h-60';
    }
  });

  protected readonly previewImageClasses = computed(() => {
    switch (this.previewSize()) {
      case 'lg':
        return 'max-h-[26rem] w-full object-contain';
      case 'md':
        return 'max-h-80 w-full object-contain';
      case 'sm':
      default:
        return 'max-h-60 w-full object-contain';
    }
  });

  private sanitizer = inject(DomSanitizer);

  constructor() {
    this.destroyRef.onDestroy(() => {
      this.cleanup();
      this.destroyViewer();
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

    // Non-PDFs: fallback to previous behavior and inform the parent
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
            this.previewUrl.set(thumb);
            this.sanitizedPreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(thumb));
          } else {
            const url = URL.createObjectURL(blob);
            this.previewUrl.set(url);
            this.sanitizedPreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(url));
          }
        } else {
          const url = URL.createObjectURL(blob);
          this.previewUrl.set(url);
          this.sanitizedPreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(url));
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
    this.documentsService.downloadDocumentFile(this.documentId()).subscribe({
      next: async (blob) => {
        this.cleanup();
        this.previewBlob.set(blob);
        this.previewMime.set(blob.type ?? null);

        // Try to generate an inline image thumbnail for PDFs for a better preview
        if (this.isPdf()) {
          const thumb = await this.generatePdfThumbnail(blob);
          if (thumb) {
            this.previewUrl.set(thumb);
            this.sanitizedPreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(thumb));
            console.debug('PDF thumbnail generated for document', this.documentId(), {
              thumbPreview: thumb.slice?.(0, 100),
            });
            this.isLoading.set(false);
            return;
          }
        }

        const url = URL.createObjectURL(blob);
        this.previewUrl.set(url);
        this.sanitizedPreview.set(this.sanitizer.bypassSecurityTrustResourceUrl(url));
        console.debug('Using blob url for preview', this.documentId(), url);
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

  private async openViewer(): Promise<void> {
    if (!this.overlayContainer) return;

    // Clear any existing viewer
    this.destroyViewer();

    // Lazy import the host component — this keeps the PDF viewer bundle out of the main chunk
    const module = await import('@/shared/components/pdf-viewer-host/pdf-viewer-host.component');
    const comp = this.overlayContainer.createComponent(module.PdfViewerHostComponent as any, {
      index: 0,
    });

    // Support both setInput API and assignment for various Angular versions
    let passedSrc: any = this.previewBlob();
    // Prefer passing the Blob directly to ngx-extended-pdf-viewer when available
    if (this.previewBlob() instanceof Blob) {
      passedSrc = this.previewBlob() as Blob;
    }

    if ((comp as any).setInput) {
      (comp as any).setInput('src', passedSrc);
    } else {
      (comp as any).instance.src = passedSrc;
    }

    // Subscribe to closed event so we can cleanup
    const compInstance: any = (comp as any).instance;
    const sub = compInstance.closed?.subscribe?.(() => {
      sub?.unsubscribe?.();
      this.destroyViewer();
    });

    this.viewerCompRef = comp;
  }

  private destroyViewer(): void {
    if (this.viewerCompRef) {
      try {
        this.viewerCompRef.destroy();
      } catch (e) {
        // ignore
      }
      this.viewerCompRef = null;
    }

    if (this.viewerUrl) {
      try {
        URL.revokeObjectURL(this.viewerUrl);
      } catch (e) {
        // ignore
      }
      this.viewerUrl = null;
    }
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
