import { signal } from '@angular/core';
import { of, Subject, throwError } from 'rxjs';
import { vi } from 'vitest';

import { type OcrStatusResponse } from '@/core/services/ocr.service';

import { CustomerFormComponent } from './customer-form.component';

describe('CustomerFormComponent OCR flow', () => {
  // use `any` to avoid TS errors when patching private/readonly fields
  type CustomerFormHarness = any;

  const createHarness = (): CustomerFormHarness => {
    const component = Object.create(CustomerFormComponent.prototype) as CustomerFormHarness;

    (component as any).ocrUseAi = signal(true);
    (component as any).ocrProcessing = signal(false);
    (component as any).ocrMessage = signal<string | null>(null);
    (component as any).ocrMessageTone = signal<'success' | 'warning' | 'error' | 'info' | null>(
      null,
    );
    (component as any).ocrData = signal<OcrStatusResponse | null>(null);
    (component as any).passportPreviewUrl = signal<string | null>(null);
    (component as any).passportPasteStatus = signal<string | null>(null);
    (component as any).passportMetadata = signal<Record<string, unknown> | null>(null);
    (component as any).ocrPollTimer = null;
    (component as any).ocrStreamSubscription = null;

    (component as any).ocrService = {
      startPassportOcr: vi.fn(),
      getOcrStatusResponse: vi.fn(),
    };
    (component as any).sseService = {
      connect: vi.fn(),
    };

    (component as any).extractOcrError = vi.fn().mockReturnValue('Upload failed');
    (component as any).handleOcrResult = vi.fn();
    (component as any).clearOcrPollTimer =
      CustomerFormComponent.prototype['clearOcrPollTimer'].bind(component);
    (component as any).clearOcrAsyncTracking =
      CustomerFormComponent.prototype['clearOcrAsyncTracking'].bind(component);
    (component as any).scheduleOcrPoll = vi.fn();
    (component as any).processOcrStatusUpdate = vi.fn().mockReturnValue(false);

    return component;
  };

  it('prefers SSE over polling when the OCR queue response includes a stream URL', () => {
    const component = createHarness();
    const subscribeToOcrStream = vi
      .spyOn(component as any, 'subscribeToOcrStream')
      .mockImplementation(() => undefined);
    const file = new File(['passport'], 'passport.png', { type: 'image/png' });

    (component as any).ocrService.startPassportOcr.mockReturnValue(
      of({
        job_id: 'job-1',
        status: 'queued',
        status_url: '/api/ocr/status/job-1/',
        stream_url: '/api/ocr/stream/job-1/',
      }),
    );

    (component as any)['runPassportImport'](file);

    expect(subscribeToOcrStream).toHaveBeenCalledWith(
      '/api/ocr/stream/job-1/',
      '/api/ocr/status/job-1/',
    );
    expect(component.scheduleOcrPoll).not.toHaveBeenCalled();
    expect(component.handleOcrResult).not.toHaveBeenCalled();
  });

  it('falls back to polling when the SSE connection fails', () => {
    const component = createHarness();

    component.ocrProcessing.set(true);
    component.sseService.connect.mockReturnValue(throwError(() => new Error('stream failed')));

    component['subscribeToOcrStream']('/api/ocr/stream/job-1/', '/api/ocr/status/job-1/');

    expect(component.scheduleOcrPoll).toHaveBeenCalledWith('/api/ocr/status/job-1/', 0);
    expect(component.ocrMessage()).toBe('Realtime connection dropped. Retrying status checks...');
    expect(component.ocrMessageTone()).toBe('warning');
  });

  it('uses SSE updates as the primary path without issuing status polls', () => {
    const component = createHarness();
    const stream$ = new Subject<OcrStatusResponse>();

    component.ocrProcessing.set(true);
    (component as any).sseService.connect.mockReturnValue(stream$);
    (component as any).processOcrStatusUpdate.mockImplementation((payload: OcrStatusResponse) => {
      if (payload.status === 'completed') {
        component.ocrProcessing.set(false);
        return true;
      }
      return false;
    });

    component['subscribeToOcrStream']('/api/ocr/stream/job-1/', '/api/ocr/status/job-1/');
    stream$.next({ status: 'processing', progress: 55, jobId: 'job-1' });
    stream$.next({
      status: 'completed',
      progress: 100,
      jobId: 'job-1',
      mrzData: { number: 'X123' },
    });

    expect((component as any).processOcrStatusUpdate).toHaveBeenCalledTimes(2);
    expect(component.scheduleOcrPoll).not.toHaveBeenCalled();
    expect((component as any).ocrService.getOcrStatusResponse).not.toHaveBeenCalled();
  });

  it('honors Retry-After when computing polling delays', () => {
    const component = createHarness();

    expect(component['computeOcrPollingDelay'](3, 7)).toBe(7000);
  });
});
