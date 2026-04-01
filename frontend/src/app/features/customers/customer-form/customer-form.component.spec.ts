import { signal } from '@angular/core';
import { of, Subject } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { type AsyncJob } from '@/core/api';
import { type OcrStatusResponse } from '@/core/services/ocr.service';

import { CustomerFormComponent } from './customer-form.component';
import { PassportOcrWorkflowService } from './passport-ocr-workflow.service';

describe('PassportOcrWorkflowService OCR flow', () => {
  type ServiceHarness = any;

  const createHarness = (): ServiceHarness => {
    const service = Object.create(PassportOcrWorkflowService.prototype) as ServiceHarness;

    service.ocrUseAi = signal(true);
    service.ocrProcessing = signal(false);
    service.ocrMessage = signal<string | null>(null);
    service.ocrMessageTone = signal<'success' | 'warning' | 'error' | 'info' | null>(null);
    service.ocrData = signal<OcrStatusResponse | null>(null);
    service.passportPreviewUrl = signal<string | null>(null);
    service.passportPasteStatus = signal<string | null>(null);
    service.passportMetadata = signal<Record<string, unknown> | null>(null);
    service.pollSub = null;

    service.ocrService = {
      startPassportOcr: vi.fn(),
    };
    service.jobService = {
      watchJob: vi.fn(),
    };

    service.extractOcrError = vi.fn().mockReturnValue('Upload failed');
    service.handleOcrResult = vi.fn();
    service.clearAsyncTracking =
      PassportOcrWorkflowService.prototype['clearAsyncTracking'].bind(service);

    return service;
  };

  it('subscribes to job updates via jobService when an OCR job starts', () => {
    const service = createHarness();
    const subscribeToOcrStream = vi
      .spyOn(service as any, 'subscribeToOcrStream')
      .mockImplementation(() => undefined);
    const file = new File(['passport'], 'passport.png', { type: 'image/png' });

    service.ocrService.startPassportOcr.mockReturnValue(
      of({
        jobId: 'job-1',
        status: 'queued',
      }),
    );

    service.startImport(file);

    expect(subscribeToOcrStream).toHaveBeenCalledWith('job-1');
    expect(service.handleOcrResult).not.toHaveBeenCalled();
  });

  it('handles job failure appropriately', () => {
    const service = createHarness();
    const stream$ = new Subject<AsyncJob>();

    service.ocrProcessing.set(true);
    service.jobService.watchJob.mockReturnValue(stream$);

    service['subscribeToOcrStream']('job-1');
    stream$.next({
      status: 'failed',
      progress: 100,
      jobId: 'job-1',
      errorMessage: 'Realtime OCR failed',
    } as unknown as AsyncJob);

    expect(service.ocrProcessing()).toBe(false);
  });

  it('uses realtime stream updates as the primary path to completion', () => {
    const service = createHarness();
    const stream$ = new Subject<AsyncJob>();

    service.ocrProcessing.set(true);
    service.jobService.watchJob.mockReturnValue(stream$);

    service['subscribeToOcrStream']('job-1');
    stream$.next({ status: 'processing', progress: 55, jobId: 'job-1' } as unknown as AsyncJob);
    stream$.next({
      status: 'completed',
      progress: 100,
      jobId: 'job-1',
      result: { number: 'X123' },
    } as unknown as AsyncJob);

    expect(service.handleOcrResult).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'completed',
        jobId: 'job-1',
        number: 'X123',
      }),
    );
  });
});

describe('CustomerFormComponent navigation after save', () => {
  type CustomerFormHarness = any;

  const createNavigationHarness = (): CustomerFormHarness => {
    const component = Object.create(CustomerFormComponent.prototype) as CustomerFormHarness;

    component.previousUrl = null;
    component.createdCustomerId = null;
    component.router = {
      navigate: vi.fn(),
      getCurrentNavigation: vi.fn().mockReturnValue(null),
    };
    component.config = {
      entityType: 'customers',
      entityLabel: 'Customer',
    };

    return component;
  };

  it('redirects updated customers to detail when opened from a non-list route', () => {
    const component = createNavigationHarness();
    component.previousUrl = '/utils/passport-check';

    component['navigateToEdit'](42);

    expect(component.router.navigate).toHaveBeenCalledWith(['/customers', 42], {
      state: {
        searchQuery: null,
        page: null,
        returnUrl: '/utils/passport-check',
      },
    });
  });

  it('keeps list-origin edit redirects unchanged', () => {
    const component = createNavigationHarness();
    component.previousUrl = '/customers';

    component['navigateToEdit'](42);

    expect(component.router.navigate).toHaveBeenCalledWith(['/customers/42/edit'], {
      state: {
        from: 'customers',
        searchQuery: null,
        page: null,
      },
    });
  });

  it('redirects created customers to detail when opened from a non-list route', () => {
    const component = createNavigationHarness();
    component.previousUrl = '/applications/7';
    component.createdCustomerId = 55;

    component['goBack']();

    expect(component.router.navigate).toHaveBeenCalledWith(['/customers', 55], {
      state: {
        searchQuery: null,
        page: null,
        returnUrl: '/applications/7',
      },
    });
  });
});
