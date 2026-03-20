import { describe, expect, it } from 'vitest';

import { mapJobUpdateToAsyncJob, type RealtimeJobUpdate } from './realtime-notification.service';

describe('mapJobUpdateToAsyncJob', () => {
  it('maps top-level job fields emitted by the backend dispatcher', () => {
    const job = mapJobUpdateToAsyncJob({
      jobId: 'job-1',
      status: 'completed',
      progress: 100,
      message: 'Passport verified successfully.',
      result: { is_valid: true },
    } as RealtimeJobUpdate);

    expect(job.jobId).toBe('job-1');
    expect(job.status).toBe('completed');
    expect(job.progress).toBe(100);
    expect(job.message).toBe('Passport verified successfully.');
    expect(job.result).toEqual({ isValid: true });
  });

  it('uses nested payload fields and canonical error messages', () => {
    const job = mapJobUpdateToAsyncJob({
      id: 'job-2',
      status: 'failed',
      progress: 100,
      payload: {
        errorMessage: 'Verification failed',
        message: 'Passport verification failed.',
      },
    } as RealtimeJobUpdate);

    expect(job.jobId).toBe('job-2');
    expect(job.errorMessage).toBe('Verification failed');
    expect(job.message).toBe('Passport verification failed.');
  });
});
