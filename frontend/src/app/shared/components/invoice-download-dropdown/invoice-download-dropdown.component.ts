import { InvoicesService } from '@/core/api/api/invoices.service';
import { AuthService } from '@/core/services/auth.service';
import { ZardButtonComponent } from '@/shared/components/button/button.component';
import {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { downloadBlob } from '@/shared/utils/file-download';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';

@Component({
  selector: 'app-invoice-download-dropdown',
  standalone: true,
  imports: [CommonModule, ...ZardDropdownImports, ZardButtonComponent, ZardIconComponent],
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

  private startAsyncPdfDownload() {
    this.loading.set(true);
    this.progress.set(0);

    this.invoicesService
      .invoicesDownloadAsyncCreate(this.invoiceId(), { format: 'pdf' })
      .subscribe({
        next: (payload: any) => {
          const streamUrl = payload?.stream_url || payload?.streamUrl;
          const downloadUrl = payload?.download_url || payload?.downloadUrl;
          if (!streamUrl) {
            this.loading.set(false);
            this.progress.set(null);
            return;
          }
          this.streamDownloadProgress(streamUrl, downloadUrl);
        },
        error: (err: any) => {
          console.error('Async download failed', err);
          this.loading.set(false);
          this.progress.set(null);
        },
      });
  }

  private async streamDownloadProgress(streamUrl: string, downloadUrl?: string) {
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

      while (true) {
        const { done, value } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });
        const events = buffer.split('\n\n');
        buffer = events.pop() || '';

        events.forEach((eventText) => {
          if (!eventText.trim()) return;
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

          if (!eventData) return;
          try {
            const data = JSON.parse(eventData);
            this.handleStreamEvent(eventType, data, downloadUrl);
          } catch (err) {
            console.error('Failed to parse download stream event', err);
          }
        });
      }
    } catch (err) {
      console.error('Download stream error', err);
      this.loading.set(false);
      this.progress.set(null);
    }
  }

  private handleStreamEvent(eventType: string, data: any, downloadUrl?: string) {
    switch (eventType) {
      case 'start':
      case 'progress': {
        const progress = typeof data.progress === 'number' ? data.progress : 0;
        this.progress.set(progress);
        break;
      }
      case 'complete': {
        this.progress.set(100);
        this.loading.set(false);
        const finalUrl = data.download_url || data.downloadUrl || downloadUrl;
        if (finalUrl) {
          window.location.assign(finalUrl);
        }
        // Hide progress bar after a short delay
        setTimeout(() => this.progress.set(null), 2000);
        break;
      }
      case 'error':
      default:
        this.loading.set(false);
        // Hide error state after a few seconds
        setTimeout(() => this.progress.set(null), 3000);
        break;
    }
  }
}
