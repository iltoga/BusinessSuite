import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { beforeEach, describe, expect, it, vi } from 'vitest';

import { InvoicesService } from '@/core/api/api/invoices.service';
import { AuthService } from '@/core/services/auth.service';
import { SseService } from '@/core/services/sse.service';

import { InvoiceDownloadDropdownComponent } from './invoice-download-dropdown.component';

describe('InvoiceDownloadDropdownComponent', () => {
  let component: InvoiceDownloadDropdownComponent;
  let invoicesServiceMock: {
    invoicesDownloadRetrieve: ReturnType<typeof vi.fn>;
    invoicesDownloadAsyncCreate: ReturnType<typeof vi.fn>;
    invoicesDownloadAsyncStatusRetrieve: ReturnType<typeof vi.fn>;
  };
  let sseServiceMock: {
    connectMessages: ReturnType<typeof vi.fn>;
  };

  beforeEach(() => {
    invoicesServiceMock = {
      invoicesDownloadRetrieve: vi.fn(),
      invoicesDownloadAsyncCreate: vi.fn(),
      invoicesDownloadAsyncStatusRetrieve: vi.fn(),
    };
    sseServiceMock = {
      connectMessages: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        { provide: InvoicesService, useValue: invoicesServiceMock },
        {
          provide: AuthService,
          useValue: {
            getToken: vi.fn(() => 'test-token'),
          },
        },
        { provide: SseService, useValue: sseServiceMock },
      ],
    });

    component = TestBed.runInInjectionContext(() => new InvoiceDownloadDropdownComponent());
    Object.assign(component as any, {
      invoiceId: () => 220,
      invoiceNumber: () => 'INV-220',
      customerName: () => 'Ada Lovelace',
    });
  });

  it('tracks async PDF generation via the invoice-specific stream URL and resolves the final download URL', async () => {
    const originalFetch = globalThis.fetch;
    invoicesServiceMock.invoicesDownloadRetrieve.mockReturnValue(
      throwError(() => new Error('sync pdf failed')),
    );
    invoicesServiceMock.invoicesDownloadAsyncCreate.mockReturnValue(
      of({
        jobId: 'job-123',
        streamUrl: '/api/invoices/download-async/stream/job-123/',
        statusUrl: '/api/invoices/download-async/status/job-123/',
        downloadUrl: '/api/invoices/download-async/file/job-123/',
      }),
    );
    sseServiceMock.connectMessages.mockReturnValue(
      of({
        event: 'complete',
        data: {
          status: 'completed',
          downloadUrl: '/api/invoices/download-async/file/job-123/',
        },
      }),
    );

    globalThis.fetch = vi.fn().mockResolvedValue({
      ok: true,
      status: 200,
      statusText: 'OK',
      headers: new Headers({ 'Content-Disposition': 'attachment; filename="invoice.pdf"' }),
      blob: () => Promise.resolve(new Blob(['pdf'], { type: 'application/pdf' })),
    } as Response);

    try {
      const result = await (component as any).generatePdfBlob(vi.fn());

      expect(sseServiceMock.connectMessages).toHaveBeenCalledWith(
        '/api/invoices/download-async/stream/job-123/',
        { useReplayCursor: true },
      );
      expect(invoicesServiceMock.invoicesDownloadAsyncStatusRetrieve).not.toHaveBeenCalled();
      expect(result.filename).toBe('invoice.pdf');
    } finally {
      globalThis.fetch = originalFetch;
    }
  });
});
