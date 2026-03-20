import { firstValueFrom, of, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { AsyncJob } from '@/core/api';
import { JobService } from './job.service';

describe('JobService.watchJob', () => {
  it('uses the per-job SSE endpoint as the primary stream', async () => {
    const service = Object.create(JobService.prototype) as any;
    service.realtimeService = {
      watchJob: vi.fn(() => of({ jobId: 'job-1', status: 'completed', progress: 100 })),
    };
    service.sseService = {
      connect: vi.fn(() =>
        of({
          jobId: 'job-1',
          status: 'processing',
          progress: 25,
          message: 'Reading passport image...',
        }),
      ),
    };

    const job = (await firstValueFrom(service.watchJob('job-1'))) as AsyncJob;

    expect(service.sseService.connect).toHaveBeenCalledWith('/api/async-jobs/status/job-1/');
    expect(service.realtimeService.watchJob).not.toHaveBeenCalled();
    expect(job.jobId).toBe('job-1');
    expect(job.progress).toBe(25);
    expect(job.message).toBe('Reading passport image...');
  });

  it('falls back to the multiplexed stream when the per-job SSE endpoint errors', async () => {
    const service = Object.create(JobService.prototype) as any;
    service.realtimeService = {
      watchJob: vi.fn(() =>
        of({
          jobId: 'job-2',
          status: 'completed',
          progress: 100,
          result: { isValid: true },
        }),
      ),
    };
    service.sseService = {
      connect: vi.fn(() => throwError(() => new Error('direct stream failed'))),
    };

    const job = (await firstValueFrom(service.watchJob('job-2'))) as AsyncJob;

    expect(service.sseService.connect).toHaveBeenCalledWith('/api/async-jobs/status/job-2/');
    expect(service.realtimeService.watchJob).toHaveBeenCalledWith('job-2');
    expect(job.jobId).toBe('job-2');
    expect(job.result).toEqual({ isValid: true });
  });
});
