import { signal } from '@angular/core';
import { of, Subject, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { type AsyncJob } from '@/core/api';
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
    (component as any).pollSub = null;
    
    (component as any).ocrService = {
      startPassportOcr: vi.fn(),
    };
    (component as any).jobService = {
      watchJob: vi.fn(),
    };

    (component as any).extractOcrError = vi.fn().mockReturnValue('Upload failed');
    (component as any).handleOcrResult = vi.fn();
    (component as any).clearOcrAsyncTracking =
      CustomerFormComponent.prototype['clearOcrAsyncTracking'].bind(component);

    return component;
  };

  it('subscribes to job updates via jobService when an OCR job starts', () => {
    const component = createHarness();
    const subscribeToOcrStream = vi
      .spyOn(component as any, 'subscribeToOcrStream')
      .mockImplementation(() => undefined);
    const file = new File(['passport'], 'passport.png', { type: 'image/png' });

    (component as any).ocrService.startPassportOcr.mockReturnValue(
      of({
        jobId: 'job-1',
        status: 'queued',
      }),
    );

    (component as any)['runPassportImport'](file);

    expect(subscribeToOcrStream).toHaveBeenCalledWith('job-1');
    expect(component.handleOcrResult).not.toHaveBeenCalled();
  });

  it('handles job failure appropriately', () => {
    const component = createHarness();
    const stream$ = new Subject<AsyncJob>();

    component.ocrProcessing.set(true);
    (component as any).jobService.watchJob.mockReturnValue(stream$);

    component['subscribeToOcrStream']('job-1');
    stream$.next({ status: 'failed', progress: 100, jobId: 'job-1', errorMessage: 'Realtime OCR failed' } as unknown as AsyncJob);

    expect(component.ocrProcessing()).toBe(false);
  });

  it('uses realtime stream updates as the primary path to completion', () => {
    const component = createHarness();
    const stream$ = new Subject<AsyncJob>();

    component.ocrProcessing.set(true);
    (component as any).jobService.watchJob.mockReturnValue(stream$);

    component['subscribeToOcrStream']('job-1');
    stream$.next({ status: 'processing', progress: 55, jobId: 'job-1' } as unknown as AsyncJob);
    stream$.next({
      status: 'completed',
      progress: 100,
      jobId: 'job-1',
      result: { number: 'X123' },
    } as unknown as AsyncJob);

    expect(component.handleOcrResult).toHaveBeenCalledWith(
      expect.objectContaining({
        status: 'completed',
        jobId: 'job-1',
        number: 'X123',
      })
    );
  });
});
