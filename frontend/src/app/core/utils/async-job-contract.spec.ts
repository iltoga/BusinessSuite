import { describe, expect, it } from 'vitest';

import {
  extractJobId,
  normalizeAsyncJobUpdate,
  normalizeJobEnvelope,
} from './async-job-contract';

describe('extractJobId', () => {
  it('prefers canonical fields and falls back to nested payloads', () => {
    expect(extractJobId({ jobId: 'job-1' })).toBe('job-1');
    expect(extractJobId({ id: 'job-2' })).toBe('job-2');
    expect(extractJobId({ payload: { jobId: 'job-3' } })).toBe('job-3');
  });
});

describe('normalizeJobEnvelope', () => {
  it('exposes a canonical jobId field only', () => {
    expect(
      normalizeJobEnvelope({
        jobId: 'job-1',
        status: 'queued',
        progress: 0,
      }),
    ).toEqual({
      jobId: 'job-1',
      status: 'queued',
      progress: 0,
    });
  });
});

describe('normalizeAsyncJobUpdate', () => {
  it('normalizes nested payload fields into AsyncJob-compatible output', () => {
    expect(
      normalizeAsyncJobUpdate({
        jobId: 'job-2',
        status: 'failed',
        progress: '100',
        payload: {
          error: 'Verification failed',
          message: 'Passport verification failed.',
        },
      }),
    ).toEqual(
      expect.objectContaining({
        id: 'job-2',
        status: 'failed',
        progress: 100,
        message: 'Passport verification failed.',
        errorMessage: 'Verification failed',
        error: 'Verification failed',
      }),
    );
  });
});
