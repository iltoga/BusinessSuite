import { InvoicesService } from '@/core/api/api/invoices.service';
import { AuthService } from '@/core/services/auth.service';
import { ZardButtonComponent } from '@/shared/components/button/button.component';
import {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { PdfViewerHostComponent } from '@/shared/components/pdf-viewer-host/pdf-viewer-host.component';
import { downloadBlob } from '@/shared/utils/file-download';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { firstValueFrom } from 'rxjs';

@Component({
  selector: 'app-invoice-download-dropdown',
  standalone: true,
  imports: [
    CommonModule,
    ...ZardDropdownImports,
    ZardButtonComponent,
    ZardIconComponent,
    PdfViewerHostComponent,
  ],
  templateUrl: './invoice-download-dropdown.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDownloadDropdownComponent {
  private invoicesService = inject(InvoicesService);
  private authService = inject(AuthService);

  invoiceId = input.required<number>();
  invoiceNumber = input.required<string>();
  customerName = input.required<string>();
  zType = input<ZardButtonTypeVariants>('secondary');
  zSize = input<ZardButtonSizeVariants>('sm');

  loading = signal(false);
  progress = signal<number | null>(null);
  printPreviewOpen = signal(false);
  printPreviewLoading = signal(false);
  printPreviewError = signal<string | null>(null);
  printPreviewBlob = signal<Blob | null>(null);
  printPreviewFilename = signal('invoice.pdf');

  download(format: 'docx' | 'pdf') {
    if (this.loading()) return;

    if (format === 'pdf') {
      this.startAsyncPdfDownload();
      return;
    }

    this.loading.set(true);
    this.progress.set(null);
    this.invoicesService.invoicesDownloadRetrieve(this.invoiceId(), format).subscribe({
      next: (blob: Blob) => {
        const filename = `${this.invoiceNumber()}_${this.customerName()}.docx`.replace(/\s+/g, '_');
        downloadBlob(blob, filename);
        this.loading.set(false);
      },
      error: (err: any) => {
        console.error('Download failed', err);
        this.loading.set(false);
      },
    });
  }

  openPrintPreview() {
    if (this.loading()) return;

    this.printPreviewOpen.set(true);
    this.printPreviewLoading.set(true);
    this.printPreviewError.set(null);
    this.printPreviewBlob.set(null);
    this.printPreviewFilename.set(this.defaultPdfFilename());
    this.loading.set(true);

    this.generatePdfBlob(() => {})
      .then(({ blob, filename }) => {
        this.printPreviewBlob.set(blob);
        this.printPreviewFilename.set(filename);
      })
      .catch((err) => {
        console.error('Print preview failed', err);
        this.printPreviewError.set('Unable to generate PDF preview. Please try again.');
      })
      .finally(() => {
        this.printPreviewLoading.set(false);
        this.loading.set(false);
      });
  }

  closePrintPreview() {
    this.printPreviewOpen.set(false);
    this.printPreviewLoading.set(false);
    this.printPreviewError.set(null);
    this.printPreviewBlob.set(null);
  }

  downloadPreviewPdf() {
    const blob = this.printPreviewBlob();
    if (!blob) {
      return;
    }
    downloadBlob(blob, this.printPreviewFilename());
  }

  private startAsyncPdfDownload() {
    this.loading.set(true);
    this.progress.set(0);

    this.generatePdfBlob((progress) => this.progress.set(progress))
      .then(({ blob, filename }) => {
        this.progress.set(100);
        downloadBlob(blob, filename);
        setTimeout(() => this.progress.set(null), 2000);
      })
      .catch((err) => {
        console.error('Async download failed', err);
        setTimeout(() => this.progress.set(null), 3000);
      })
      .finally(() => {
        this.loading.set(false);
      });
  }

  private async generatePdfBlob(
    onProgress: (progress: number) => void,
  ): Promise<{ blob: Blob; filename: string }> {
    const payload = await firstValueFrom(
      this.invoicesService.invoicesDownloadAsyncCreate(this.invoiceId(), { format: 'pdf' }),
    );
    const streamUrl = payload?.['stream_url'] || payload?.['streamUrl'];
    const downloadUrl = payload?.['download_url'] || payload?.['downloadUrl'];

    if (!streamUrl) {
      throw new Error('Missing stream URL in PDF generation response');
    }

    const finalUrl = await this.streamDownloadProgress(streamUrl, downloadUrl, onProgress);
    return this.fetchFile(finalUrl);
  }

  private async streamDownloadProgress(
    streamUrl: string,
    downloadUrl: string | undefined,
    onProgress: (progress: number) => void,
  ): Promise<string> {
    try {
      const token = this.authService.getToken();
      const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};
      const response = await fetch(streamUrl, {
        headers,
        credentials: 'same-origin',
      });

      if (!response.ok || !response.body) {
        throw new Error('Unable to open download stream');
      }

      const reader = response.body.getReader();
      const decoder = new TextDecoder();
      let buffer = '';
      const processEvent = (eventText: string): string | null => {
        if (!eventText.trim()) return null;
        const lines = eventText.split('\n');
        let eventType = 'message';
        let eventData = '';
        lines.forEach((line) => {
          if (line.startsWith('event: ')) {
            eventType = line.substring(7);
          } else if (line.startsWith('data: ')) {
            eventData = line.substring(6);
          }
        });

        if (!eventData) return null;
        let data: any;
        try {
          data = JSON.parse(eventData);
        } catch (err) {
          console.error('Failed to parse download stream event', err);
          throw err;
        }
        const result = this.handleStreamEvent(eventType, data, downloadUrl, onProgress);
        if (result.status === 'complete') {
          return result.url;
        }
        if (result.status === 'error') {
          throw new Error(result.message);
        }
        return null;
      };

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        for (const eventText of events) {
          const completedUrl = processEvent(eventText);
          if (completedUrl) {
            return completedUrl;
          }
        }
      }

      if (buffer.trim()) {
        const trailingEvents = buffer.split('\n\n').filter((eventText) => eventText.trim());
        for (const eventText of trailingEvents) {
          const completedUrl = processEvent(eventText);
          if (completedUrl) {
            return completedUrl;
          }
        }
      }

      throw new Error('Download stream closed before completion');
    } catch (err) {
      console.error('Download stream error', err);
      throw err;
    }
  }

  private handleStreamEvent(
    eventType: string,
    data: any,
    downloadUrl: string | undefined,
    onProgress: (progress: number) => void,
  ):
    | { status: 'continue' }
    | { status: 'complete'; url: string }
    | { status: 'error'; message: string } {
    switch (eventType) {
      case 'start':
      case 'progress': {
        const progress = typeof data.progress === 'number' ? data.progress : 0;
        onProgress(progress);
        return { status: 'continue' };
      }
      case 'complete': {
        const finalUrl = data.download_url || data.downloadUrl || downloadUrl;
        if (!finalUrl) {
          return {
            status: 'error',
            message: 'PDF generation completed without a download URL',
          };
        }
        return { status: 'complete', url: finalUrl };
      }
      case 'error':
      default:
        return {
          status: 'error',
          message: data?.message || data?.detail || 'PDF generation failed',
        };
    }
  }

  private async fetchFile(url: string): Promise<{ blob: Blob; filename: string }> {
    const token = this.authService.getToken();
    const headers: HeadersInit = token ? { Authorization: `Bearer ${token}` } : {};

    const response = await fetch(url, {
      headers,
      credentials: 'same-origin',
    });

    if (!response.ok) {
      throw new Error(`Failed to download file: ${response.status} ${response.statusText}`);
    }

    const blob = await response.blob();
    const filename = this.extractFilename(response.headers.get('Content-Disposition') || '', url);
    return { blob, filename };
  }

  private extractFilename(contentDisposition: string, fallbackUrl: string): string {
    let filename = `${this.invoiceNumber()}_${this.customerName()}`.replace(/\s+/g, '_');
    const match = /filename\*?=(?:UTF-8'')?"?([^";]*)"?/.exec(contentDisposition);
    if (match && match[1]) {
      try {
        filename = decodeURIComponent(match[1]);
      } catch (e) {
        filename = match[1];
      }
    } else {
      // fallback to PDF extension
      const ext = fallbackUrl.endsWith('.docx') ? 'docx' : 'pdf';
      filename = `${filename}.${ext}`;
    }
    return filename;
  }

  private defaultPdfFilename(): string {
    return `${this.invoiceNumber()}_${this.customerName()}.pdf`.replace(/\s+/g, '_');
  }
}
