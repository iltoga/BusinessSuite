
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
import { downloadBlob } from '@/shared/utils/file-download';
import { ZardButtonComponent } from '@/shared/components/button/button.component';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { ZardSkeletonComponent } from '@/shared/components/skeleton';

@Component({
  selector: 'app-pdf-viewer-host',
  standalone: true,
  imports: [
    NgxExtendedPdfViewerModule,
    ZardButtonComponent,
    ZardIconComponent,
    ZardSkeletonComponent
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
    // Always use the same print strategy as the legacy Document Print view:
    // render a blob-backed PDF and call window.print() from an iframe.
    this.openAndPrintBlobFallback();
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

  private async openAndPrintBlobFallback(): Promise<void> {
    // Determine a Blob for the current src
    try {
      let blob: Blob | null = null;

      if (!this.src) {
        // Nothing to print, try window.print() as a last resort
        try {
          window.print();
        } catch (e) {
          console.error('Failed to print', e);
        }
        return;
      }

      if (this.src instanceof Blob) {
        blob = this.src;
      } else if (typeof this.src === 'string') {
        // Try to fetch the resource as a blob (works for same-origin URLs)
        try {
          const res = await fetch(this.src, { credentials: 'same-origin' });
          if (res.ok) blob = await res.blob();
        } catch (e) {
          console.warn('Failed to fetch PDF to create blob fallback', e);
        }
      }

      if (!blob) {
        // As a final fallback, open the URL in a new tab so user can print manually
        const href = this.href || (this.src as string);
        try {
          window.open(href, '_blank');
        } catch (e) {
          console.error('Failed to open fallback PDF in new tab', e);
        }
        return;
      }

      const blobUrl = URL.createObjectURL(blob);

      // Try an invisible iframe print approach (same technique used in the
      // existing Document Print view that works reliably in app browsers).
      try {
        const iframe = document.createElement('iframe');
        iframe.style.position = 'fixed';
        iframe.style.right = '0';
        iframe.style.bottom = '0';
        iframe.style.width = '0px';
        iframe.style.height = '0px';
        iframe.style.border = '0';
        iframe.src = blobUrl;

        const cleanup = () => {
          try {
            if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
          } catch (e) {}
          try {
            URL.revokeObjectURL(blobUrl);
          } catch (e) {}
        };

        iframe.onload = () => {
          try {
            const w = iframe.contentWindow;
            if (w) {
              w.focus();
              // Delay slightly to ensure the PDF renders inside the iframe
              setTimeout(() => {
                try {
                  w.print();
                } catch (e) {
                  console.error('Iframe print failed, falling back to new-window method', e);
                  // Fallback to opening a new tab
                  openInNewWindowPrint(blobUrl).finally(cleanup);
                } finally {
                  // Cleanup after a short delay
                  setTimeout(cleanup, 1000);
                }
              }, 500);
            } else {
              // No content window, fallback
              openInNewWindowPrint(blobUrl).finally(cleanup);
            }
          } catch (e) {
            console.error('Error during iframe print, falling back', e);
            openInNewWindowPrint(blobUrl).finally(cleanup);
          }
        };

        document.body.appendChild(iframe);
      } catch (e) {
        console.error('Creating iframe print fallback failed, opening new window', e);
        try {
          await openInNewWindowPrint(blobUrl);
        } finally {
          try {
            URL.revokeObjectURL(blobUrl);
          } catch (e) {}
        }
      }

      // Helper: open a new window with an embedded PDF that auto-invokes print
      async function openInNewWindowPrint(url: string): Promise<void> {
        const html = `
          <!doctype html>
          <html>
            <head>
              <meta charset="utf-8" />
              <title>PDF Print</title>
              <style>html,body{height:100%;margin:0}</style>
            </head>
            <body>
              <embed src="${url}" type="application/pdf" width="100%" height="100%" />
              <script>
                (function() {
                  const doPrint = () => {
                    try { window.focus(); window.print(); } catch (e) { console.error(e); }
                  };
                  setTimeout(doPrint, 500);
                })();
              </script>
            </body>
          </html>
        `;

        const w = window.open('', '_blank');
        if (!w) {
          throw new Error('Popup blocked; cannot open print fallback window');
        }
        w.document.write(html);
        return new Promise((resolve) => setTimeout(resolve, 1000));
      }
    } catch (e) {
      console.error('openAndPrintBlobFallback failed', e);
      try {
        window.print();
      } catch (e2) {
        console.error('Final print fallback failed', e2);
      }
    }
  }
}
