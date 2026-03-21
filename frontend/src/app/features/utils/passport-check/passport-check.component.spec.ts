import { signal } from '@angular/core';
import { Subject } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { PassportCheckComponent } from './passport-check.component';

describe('PassportCheckComponent passport result normalization', () => {
  type PassportCheckHarness = any;

  const createHarness = (): PassportCheckHarness => {
    const component = Object.create(PassportCheckComponent.prototype) as PassportCheckHarness;

    (component as any).selectedFile = signal<File | null>(null);
    (component as any).previewUrl = signal<string | null>(null);
    (component as any).previewType = signal<'image' | 'pdf' | 'unknown'>('unknown');
    (component as any).method = signal<'ai' | 'hybrid'>('hybrid');
    (component as any).isChecking = signal(false);
    (component as any).progress = signal(0);
    (component as any).progressMessage = signal('');
    (component as any).processSteps = signal<string[]>([]);
    (component as any).result = signal<Record<string, unknown> | null>(null);
    (component as any).actionInProgress = signal(false);
    (component as any).actionTargetCustomerId = signal<number | null>(null);
    (component as any).jobProgressSubscription = null;

    (component as any).jobService = {
      watchJob: vi.fn(),
    };
    (component as any).toast = {
      error: vi.fn(),
    };

    return component;
  };

  it('normalizes camelCase async-job results so the UI shows the real rejection details', () => {
    const component = createHarness();
    const stream$ = new Subject<any>();

    component.isChecking.set(true);
    component.jobService.watchJob.mockReturnValue(stream$);

    component['listenToJobProgress']('job-1');

    stream$.next({
      status: 'completed',
      progress: 100,
      jobId: 'job-1',
      message: 'Passport verification failed.',
      result: {
        isValid: false,
        methodUsed: 'hybrid (deterministic+ai)',
        modelUsed: 'qwen/qwen3.5-flash-02-23',
        rejectionCode: 'invalid_passport_number',
        rejectionReason: 'Extracted passport number is invalid: Passport number appears to contain MRZ data.',
        rejectionReasons: [
          'Extracted passport number is invalid: Passport number appears to contain MRZ data.',
        ],
        passportData: {
          firstName: 'Anna',
          lastName: 'Maria',
          nationalityCode: 'ITA',
          passportNumber: 'YC5428855',
          expirationDate: '2034-05-14',
          confidenceScore: 0.82,
        },
        customerMatch: {
          status: 'no_match',
          message: 'No existing customer matched.',
          passportNumber: 'YC5428855',
          exactMatches: [],
          similarMatches: [],
          recommendedAction: 'create_customer',
        },
      },
    });

    expect(component.isChecking()).toBe(false);
    expect(component.progress()).toBe(100);
    expect(component.progressMessage()).toBe('Passport verification failed.');
    expect(component.jobService.watchJob).toHaveBeenCalledWith('job-1');
    expect(component.result()).toEqual(
      expect.objectContaining({
        is_valid: false,
        method_used: 'hybrid (deterministic+ai)',
        model_used: 'qwen/qwen3.5-flash-02-23',
        rejection_code: 'invalid_passport_number',
        rejection_reason:
          'Extracted passport number is invalid: Passport number appears to contain MRZ data.',
        rejection_reasons: [
          'Extracted passport number is invalid: Passport number appears to contain MRZ data.',
        ],
        passport_data: expect.objectContaining({
          first_name: 'Anna',
          last_name: 'Maria',
          nationality_code: 'ITA',
          passport_number: 'YC5428855',
          expiration_date: '2034-05-14',
          confidence_score: 0.82,
        }),
        customer_match: expect.objectContaining({
          status: 'no_match',
          message: 'No existing customer matched.',
          passport_number: 'YC5428855',
          recommended_action: 'create_customer',
        }),
      }),
    );
    expect(component['getDisplayRejectionReason']()).toBe(
      'Extracted passport number is invalid: Passport number appears to contain MRZ data.',
    );
  });
});
