import { describe, expect, it } from 'vitest';

import { mapJobUpdateToAsyncJob, type RealtimeJobUpdate } from './realtime-notification.service';

describe('mapJobUpdateToAsyncJob', () => {
  it('maps top-level job fields emitted by the backend dispatcher', () => {
    const job = mapJobUpdateToAsyncJob({
      job_id: 'job-1',
      status: 'completed',
      progress: 100,
      message: 'Passport verified successfully.',
      result: { is_valid: true },
    } as RealtimeJobUpdate);

    expect(job.id).toBe('job-1');
    expect(job.status).toBe('completed');
    expect(job.progress).toBe(100);
    expect((job as any).message).toBe('Passport verified successfully.');
    expect((job as any).result).toEqual({ is_valid: true });
  });

  it('falls back to nested payload fields for older event shapes', () => {
    const job = mapJobUpdateToAsyncJob({
      job_id: 'job-2',
      status: 'failed',
      progress: 100,
      payload: {
        error: 'Verification failed',
        message: 'Passport verification failed.',
      },
    } as RealtimeJobUpdate);

    expect(job.id).toBe('job-2');
    expect((job as any).errorMessage).toBe('Verification failed');
    expect((job as any).message).toBe('Passport verification failed.');
  });
});
