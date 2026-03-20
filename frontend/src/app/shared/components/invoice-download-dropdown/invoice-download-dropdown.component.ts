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
import { JobService } from '@/core/services/job.service';
import { firstValueFrom, Subscription } from 'rxjs';

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
  private jobService = inject(JobService);

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
    try {
      // Prefer direct PDF download to avoid hard dependency on background workers.
      return await this.fetchSyncPdfBlob(onProgress);
    } catch (syncErr) {
      console.warn('Direct PDF download failed, attempting async flow', syncErr);
    }

    try {
      const payload = await firstValueFrom(
        this.invoicesService.invoicesDownloadAsyncCreate(this.invoiceId(), { format: 'pdf' }),
      );
      const jobId = payload?.['jobId'] || payload?.['id'];
      const downloadUrl = payload?.['downloadUrl'] || payload?.['download_url'];
      let finalUrl: string;

      if (jobId) {
        finalUrl = await this.trackJobStatus(jobId, downloadUrl, onProgress);
      } else {
        throw new Error('Missing job ID in PDF generation response');
      }

      return this.fetchFile(finalUrl);
    } catch (err) {
      console.error('Async PDF flow failed', err);
      throw err;
    }
  }

  private async trackJobStatus(
    jobId: string,
    downloadUrl: string | undefined,
    onProgress: (progress: number) => void,
  ): Promise<string> {
    return new Promise((resolve, reject) => {
      let sub: Subscription | null = null;
      sub = this.jobService.watchJob(jobId).subscribe({
        next: (jobStatus) => {
          if (typeof jobStatus.progress === 'number') {
            onProgress(jobStatus.progress);
          }
          if (jobStatus.status === 'completed') {
            const result = jobStatus.result as Record<string, any> | undefined;
            const finalUrl =
              result?.['download_url'] || result?.['downloadUrl'] || downloadUrl;
            if (!finalUrl) {
              sub?.unsubscribe();
              reject(new Error('PDF generation completed without a download URL'));
              return;
            }
            sub?.unsubscribe();
            resolve(finalUrl as string);
          } else if (jobStatus.status === 'failed') {
            const result = jobStatus.result as Record<string, any> | undefined;
            sub?.unsubscribe();
            reject(new Error((result?.['error'] as string) || 'PDF generation failed'));
          }
        },
        error: (err) => {
          sub?.unsubscribe();
          reject(err);
        },
      });
    });
  }

  private async fetchSyncPdfBlob(
    onProgress: (progress: number) => void,
  ): Promise<{ blob: Blob; filename: string }> {
    onProgress(5);
    const blob = await firstValueFrom(this.invoicesService.invoicesDownloadRetrieve(this.invoiceId(), 'pdf'));
    onProgress(100);
    return { blob, filename: this.defaultPdfFilename() };
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

  private sleep(ms: number): Promise<void> {
    return new Promise((resolve) => {
      setTimeout(resolve, ms);
    });
  }
}
