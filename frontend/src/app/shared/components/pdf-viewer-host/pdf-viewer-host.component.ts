import { ZardButtonComponent } from '@/shared/components/button/button.component';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { ZardSkeletonComponent } from '@/shared/components/skeleton';
import { downloadBlob } from '@/shared/utils/file-download';
import { openPdfPrintPreview } from '@/shared/utils/pdf-print-preview';
import {
  ChangeDetectionStrategy,
  Component,
  ElementRef,
  EventEmitter,
  HostListener,
  Input,
  OnChanges,
  OnDestroy,
  OnInit,
  Output,
  Renderer2,
  inject,
} from '@angular/core';
import { NgxExtendedPdfViewerModule, pdfDefaultOptions } from 'ngx-extended-pdf-viewer';

@Component({
  selector: 'app-pdf-viewer-host',
  standalone: true,
  imports: [
    NgxExtendedPdfViewerModule,
    ZardButtonComponent,
    ZardIconComponent,
    ZardSkeletonComponent,
  ],
  templateUrl: './pdf-viewer-host.component.html',
  styleUrls: ['./pdf-viewer-host.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class PdfViewerHostComponent implements OnChanges, OnInit, OnDestroy {
  @Input() src: Blob | string | null = null;
  @Input() isBusy = false;
  @Input() errorMessage: string | null = null;
  @Input() showDownloadButton = false;
  @Input() downloadFileName = 'document.pdf';
  @Input() appendToBody = true;
  @Output() closed = new EventEmitter<void>();
  @Output() downloadRequested = new EventEmitter<void>();

  isLoading = true;
  loadError: string | null = null;
  private blobUrl: string | null = null;

  private el = inject(ElementRef);
  private renderer = inject(Renderer2);

  ngOnInit(): void {
    if (this.appendToBody && typeof document !== 'undefined') {
      this.renderer.appendChild(document.body, this.el.nativeElement);
    }
  }

  ngOnDestroy(): void {
    if (this.el.nativeElement && this.el.nativeElement.parentNode) {
      this.renderer.removeChild(this.el.nativeElement.parentNode, this.el.nativeElement);
    }
  }

  ngOnChanges(): void {
    if (this.isBusy) {
      this.isLoading = true;
      this.loadError = null;
      return;
    }

    if (!this.src) {
      this.isLoading = false;
      this.loadError = null;
      return;
    }

    this.isLoading = true;
    this.loadError = null;
  }

  constructor() {
    // Ensure the ngx-extended-pdf-viewer assets and worker are loaded from local assets
    try {
      pdfDefaultOptions.assetsFolder = 'assets';
      pdfDefaultOptions.workerSrc = () => '/assets/pdf.worker-5.4.1105.min.mjs';
    } catch (e) {
      console.debug('Unable to set pdfDefaultOptions, will rely on pdfjs auto-detection', e);
    }
  }

  close(): void {
    this.destroyBlobUrl();
    this.closed.emit();
  }

  @HostListener('document:keydown.escape', ['$event'])
  onEscape(event: Event): void {
    if (typeof event.stopImmediatePropagation === 'function') {
      event.stopImmediatePropagation();
    } else {
      event.stopPropagation();
    }
    event.preventDefault();
    this.close();
  }

  get href(): string {
    if (!this.src) return '';
    if (typeof this.src === 'string') return this.src;
    if (this.src instanceof Blob) {
      if (!this.blobUrl) this.blobUrl = URL.createObjectURL(this.src);
      return this.blobUrl;
    }
    return '';
  }

  private destroyBlobUrl(): void {
    if (this.blobUrl) {
      try {
        URL.revokeObjectURL(this.blobUrl);
      } catch (e) {
        // ignore
      }
      this.blobUrl = null;
    }
  }

  onAfterLoadComplete(event: any): void {
    console.debug('ngx-extended-pdf-viewer loaded', event);
    this.isLoading = false;
    this.loadError = null;
  }

  onProgress(event: any): void {
    // event.percent, event.page, event.total
    console.debug('ngx-extended-pdf-viewer progress', event);
    if (event && typeof event.percent === 'number') {
      this.isLoading = event.percent < 100;
    }
  }

  onLoadFailed(event: any): void {
    console.error('ngx-extended-pdf-viewer failed to load PDF', event);
    this.loadError = 'PDF rendering failed. You can open the file in a new tab.';
    this.isLoading = false;
  }

  print(): void {
    if (this.isBusy || !this.src) {
      return;
    }
    void openPdfPrintPreview(this.src);
  }

  download(): void {
    if (this.isBusy || !this.src) {
      return;
    }

    if (this.downloadRequested.observers.length > 0) {
      this.downloadRequested.emit();
      return;
    }

    if (this.src instanceof Blob) {
      downloadBlob(this.src, this.downloadFileName || 'document.pdf');
      return;
    }

    const href = this.href;
    if (!href) {
      return;
    }

    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = this.downloadFileName || 'document.pdf';
    anchor.target = '_blank';
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }
}
