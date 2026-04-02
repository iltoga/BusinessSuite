import { InvoicesService } from '@/core/api/api/invoices.service';
import { AsyncJobStatusEnum } from '@/core/api/model/async-job';
import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';
import { ZardButtonComponent } from '@/shared/components/button/button.component';
import {
  ZardButtonSizeVariants,
  ZardButtonTypeVariants,
} from '@/shared/components/button/button.variants';
import { ZardDropdownImports } from '@/shared/components/dropdown/dropdown.imports';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { PdfViewerHostComponent } from '@/shared/components/pdf-viewer-host/pdf-viewer-host.component';
import { ZardSkeletonComponent } from '@/shared/components/skeleton';
import { downloadBlob } from '@/shared/utils/file-download';

import {
  camelizePayload,
  extractJobId,
  isRecord,
  toOptionalNumber,
  toOptionalString,
} from '@/core/utils/async-job-contract';
import { ChangeDetectionStrategy, Component, inject, input, signal } from '@angular/core';
import { firstValueFrom, Subscription } from 'rxjs';

type InvoiceDownloadTracking = {
  jobId: string;
  streamUrl?: string;
  statusUrl?: string;
  downloadUrl?: string;
};

type InvoiceDownloadProgress = {
  status?: string;
  progress?: number;
  downloadUrl?: string;
  errorMessage?: string;
  message?: string;
};

@Component({
  selector: 'app-invoice-download-dropdown',
  standalone: true,
  imports: [
    ...ZardDropdownImports,
    ZardButtonComponent,
    ZardIconComponent,
    ZardSkeletonComponent,
    PdfViewerHostComponent,
  ],
  templateUrl: './invoice-download-dropdown.component.html',
  styleUrls: ['./invoice-download-dropdown.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class InvoiceDownloadDropdownComponent {
  private invoicesService = inject(InvoicesService);
  private authService = inject(AuthService);
  private sseService = inject(SseService);

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
    this.invoicesService
      .invoicesDownloadRetrieve({ id: this.invoiceId(), fileFormat: format })
      .subscribe({
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
        this.invoicesService.invoicesDownloadAsyncCreate({
          id: this.invoiceId(),
          requestBody: { format: 'pdf' },
        }),
      );
      const tracking = this.extractTrackingInfo(payload);

      if (!tracking) {
        throw new Error('Missing job ID in PDF generation response');
      }

      const finalUrl = await this.trackJobStatus(tracking, onProgress);

      return this.fetchFile(finalUrl);
    } catch (err) {
      console.error('Async PDF flow failed', err);
      throw err;
    }
  }

  private extractTrackingInfo(payload: unknown): InvoiceDownloadTracking | null {
    const record = isRecord(payload) ? (camelizePayload(payload) as Record<string, unknown>) : null;
    const jobId = extractJobId(record ?? payload);
    if (!jobId) {
      return null;
    }

    return {
      jobId,
      streamUrl: toOptionalString(record?.['streamUrl']),
      statusUrl: toOptionalString(record?.['statusUrl']),
      downloadUrl: toOptionalString(record?.['downloadUrl']),
    };
  }

  private normalizeDownloadProgress(payload: unknown): InvoiceDownloadProgress {
    const record = isRecord(payload) ? (camelizePayload(payload) as Record<string, unknown>) : {};
    return {
      status: toOptionalString(record['status']),
      progress: toOptionalNumber(record['progress']),
      downloadUrl: toOptionalString(record['downloadUrl']),
      errorMessage: toOptionalString(record['errorMessage']) ?? toOptionalString(record['error']),
      message: toOptionalString(record['message']),
    };
  }

  private async trackJobStatus(
    tracking: InvoiceDownloadTracking,
    onProgress: (progress: number) => void,
  ): Promise<string> {
    const streamUrl = tracking.streamUrl;
    if (!streamUrl) {
      return this.pollJobStatus(tracking, onProgress);
    }

    return new Promise((resolve, reject) => {
      let settled = false;
      let sub: Subscription | null = null;
      const settleResolve = (value: string) => {
        if (settled) {
          return;
        }
        settled = true;
        resolve(value);
      };
      const settleReject = (error: unknown) => {
        if (settled) {
          return;
        }
        settled = true;
        reject(error);
      };

      const resolveFromStatus = () => {
        void this.pollJobStatus(tracking, onProgress).then(settleResolve).catch(settleReject);
      };

      sub = this.sseService
        .connectMessages<unknown>(streamUrl, { useReplayCursor: true })
        .subscribe({
          next: (message) => {
            const update = this.normalizeDownloadProgress(message.data);
            if (typeof update.progress === 'number') {
              onProgress(update.progress);
            }

            if (message.event === 'complete' || update.status === AsyncJobStatusEnum.Completed) {
              const finalUrl = update.downloadUrl || tracking.downloadUrl;
              if (!finalUrl) {
                sub?.unsubscribe();
                resolveFromStatus();
                return;
              }
              sub?.unsubscribe();
              settleResolve(finalUrl);
            } else if (message.event === 'error' || update.status === AsyncJobStatusEnum.Failed) {
              sub?.unsubscribe();
              settleReject(
                new Error(update.errorMessage || update.message || 'PDF generation failed'),
              );
            }
          },
          error: () => {
            sub?.unsubscribe();
            resolveFromStatus();
          },
          complete: () => {
            if (!settled) {
              resolveFromStatus();
            }
          },
        });
    });
  }

  private async pollJobStatus(
    tracking: InvoiceDownloadTracking,
    onProgress: (progress: number) => void,
  ): Promise<string> {
    for (let attempt = 0; attempt < 60; attempt += 1) {
      const payload = await firstValueFrom(
        this.invoicesService.invoicesDownloadAsyncStatusRetrieve({ jobId: tracking.jobId }),
      );
      const update = this.normalizeDownloadProgress(payload);

      if (typeof update.progress === 'number') {
        onProgress(update.progress);
      }

      if (update.status === AsyncJobStatusEnum.Completed) {
        const finalUrl = update.downloadUrl || tracking.downloadUrl;
        if (!finalUrl) {
          throw new Error('PDF generation completed without a download URL');
        }
        return finalUrl;
      }

      if (update.status === AsyncJobStatusEnum.Failed) {
        throw new Error(update.errorMessage || update.message || 'PDF generation failed');
      }

      await this.sleep(1000);
    }

    throw new Error('PDF generation tracking stopped before completion');
  }

  private async fetchSyncPdfBlob(
    onProgress: (progress: number) => void,
  ): Promise<{ blob: Blob; filename: string }> {
    onProgress(5);
    const blob = await firstValueFrom(
      this.invoicesService.invoicesDownloadRetrieve({ id: this.invoiceId(), fileFormat: 'pdf' }),
    );
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
