
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
import { downloadBlob } from '@/shared/utils/file-download';
import { ZardButtonComponent } from '@/shared/components/button/button.component';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { ZardSkeletonComponent } from '@/shared/components/skeleton';

@Component({
  selector: 'app-image-viewer-host',
  standalone: true,
  imports: [
    ZardButtonComponent,
    ZardIconComponent,
    ZardSkeletonComponent
],
  templateUrl: './image-viewer-host.component.html',
  styleUrls: ['./image-viewer-host.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ImageViewerHostComponent implements OnChanges, OnInit, OnDestroy {
  @Input() src: Blob | string | null = null;
  @Input() isBusy = false;
  @Input() errorMessage: string | null = null;
  @Input() showDownloadButton = false;
  @Input() downloadFileName = 'document.png';
  @Input() appendToBody = true;
  @Output() closed = new EventEmitter<void>();

  isLoading = true;
  loadError: string | null = null;
  imageUrl: string | null = null;

  private blobUrl: string | null = null;

  private el = inject(ElementRef);
  private renderer = inject(Renderer2);

  ngOnInit(): void {
    if (this.appendToBody && typeof document !== 'undefined') {
      this.renderer.appendChild(document.body, this.el.nativeElement);
    }
  }

  ngOnDestroy(): void {
    this.destroyBlobUrl();
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
      this.imageUrl = null;
      return;
    }

    this.isLoading = true;
    this.loadError = null;
    this.prepareImageUrl();
  }

  close(): void {
    this.destroyBlobUrl();
    this.closed.emit();
  }

  @HostListener('document:keydown.escape', ['$event'])
  onEscape(event: Event): void {
    if (typeof (event as KeyboardEvent).stopImmediatePropagation === 'function') {
      (event as KeyboardEvent).stopImmediatePropagation();
    } else {
      event.stopPropagation();
    }
    event.preventDefault();
    this.close();
  }

  onImageLoad(): void {
    this.isLoading = false;
    this.loadError = null;
  }

  onImageError(): void {
    this.isLoading = false;
    this.loadError = 'Failed to load image. You can try downloading the file.';
  }

  download(): void {
    if (this.isBusy || !this.src) {
      return;
    }

    if (this.src instanceof Blob) {
      downloadBlob(this.src, this.downloadFileName || 'document.png');
      return;
    }

    const href = this.imageUrl;
    if (!href) {
      return;
    }

    const anchor = document.createElement('a');
    anchor.href = href;
    anchor.download = this.downloadFileName || 'document.png';
    anchor.target = '_blank';
    anchor.rel = 'noopener';
    document.body.appendChild(anchor);
    anchor.click();
    document.body.removeChild(anchor);
  }

  print(): void {
    if (this.isBusy || !this.imageUrl) {
      return;
    }

    const url = this.imageUrl;
    try {
      const iframe = document.createElement('iframe');
      iframe.style.position = 'fixed';
      iframe.style.right = '0';
      iframe.style.bottom = '0';
      iframe.style.width = '0px';
      iframe.style.height = '0px';
      iframe.style.border = '0';

      const cleanup = () => {
        try {
          if (iframe.parentNode) iframe.parentNode.removeChild(iframe);
        } catch (e) {}
      };

      iframe.onload = () => {
        try {
          const w = iframe.contentWindow;
          if (w) {
            w.focus();
            setTimeout(() => {
              try {
                w.print();
              } catch (e) {
                console.error('Iframe print failed', e);
              } finally {
                setTimeout(cleanup, 1000);
              }
            }, 500);
          }
        } catch (e) {
          console.error('Error during iframe print', e);
          cleanup();
        }
      };

      const html = `
        <!doctype html>
        <html>
          <head>
            <meta charset="utf-8" />
            <title>Image Print</title>
            <style>
              html, body { height: 100%; margin: 0; display: flex; align-items: center; justify-content: center; }
              img { max-width: 100%; max-height: 100%; object-fit: contain; }
              @media print {
                html, body { height: auto; }
                img { max-width: 100%; max-height: 100vh; }
              }
            </style>
          </head>
          <body>
            <img src="${url}" />
          </body>
        </html>
      `;
      iframe.srcdoc = html;
      document.body.appendChild(iframe);
    } catch (e) {
      console.error('Print failed', e);
    }
  }

  private prepareImageUrl(): void {
    this.destroyBlobUrl();

    if (!this.src) {
      this.imageUrl = null;
      return;
    }

    if (typeof this.src === 'string') {
      this.imageUrl = this.src;
      return;
    }

    if (this.src instanceof Blob) {
      this.blobUrl = URL.createObjectURL(this.src);
      this.imageUrl = this.blobUrl;
      return;
    }

    this.imageUrl = null;
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
}
