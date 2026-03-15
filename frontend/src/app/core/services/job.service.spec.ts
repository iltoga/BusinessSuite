import { NEVER, firstValueFrom, of, throwError } from 'rxjs';
import { afterEach, describe, expect, it, vi } from 'vitest';

import { JobService } from './job.service';

describe('JobService.watchJob', () => {
  afterEach(() => {
    vi.useRealTimers();
  });

  it('falls back to the per-job SSE endpoint when the multiplexed stream stays silent', async () => {
    vi.useFakeTimers();

    const service = Object.create(JobService.prototype) as any;
    service.realtimeService = {
      watchJob: vi.fn(() => NEVER),
    };
    service.sseService = {
      connect: vi.fn(() =>
        of({
          id: 'job-1',
          status: 'processing',
          progress: 25,
          message: 'Reading passport image...',
        }),
      ),
    };

    const resultPromise = firstValueFrom(service.watchJob('job-1'));
    await vi.advanceTimersByTimeAsync(1600);

    const job = await resultPromise;

    expect(service.realtimeService.watchJob).toHaveBeenCalledWith('job-1');
    expect(service.sseService.connect).toHaveBeenCalledWith('/api/async-jobs/status/job-1/');
    expect(job.id).toBe('job-1');
    expect(job.progress).toBe(25);
    expect((job as any).message).toBe('Reading passport image...');
  });

  it('falls back to the per-job SSE endpoint when the multiplexed stream errors', async () => {
    const service = Object.create(JobService.prototype) as any;
    service.realtimeService = {
      watchJob: vi.fn(() => throwError(() => new Error('global stream failed'))),
    };
    service.sseService = {
      connect: vi.fn(() =>
        of({
          id: 'job-2',
          status: 'completed',
          progress: 100,
          result: { is_valid: true },
        }),
      ),
    };

    const job = await firstValueFrom(service.watchJob('job-2'));

    expect(service.sseService.connect).toHaveBeenCalledWith('/api/async-jobs/status/job-2/');
    expect(job.id).toBe('job-2');
    expect((job as any).result).toEqual({ is_valid: true });
  });
});
