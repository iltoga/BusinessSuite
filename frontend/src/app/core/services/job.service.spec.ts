import { firstValueFrom, of, Subject, throwError, takeWhile } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import { AsyncJob } from '@/core/api';
import { JobService } from './job.service';

type JobUpdate = {
  jobId: string;
  status: AsyncJob.StatusEnum;
  progress: number;
  result?: Record<string, unknown>;
};

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

  it('completes the direct job stream after the terminal update', () => {
    const updates$ = new Subject<JobUpdate>();
    const service = Object.create(JobService.prototype) as any;
    service.realtimeService = {
      watchJob: vi.fn(),
    };
    service.sseService = {
      connect: vi.fn(() => updates$.asObservable()),
    };

    const nextSpy = vi.fn();
    const completeSpy = vi.fn();
    const sub = service.watchJob('job-1').subscribe({
      next: nextSpy,
      complete: completeSpy,
    });

    updates$.next({ jobId: 'job-1', status: 'processing', progress: 25 });
    expect(completeSpy).not.toHaveBeenCalled();

    updates$.next({ jobId: 'job-1', status: 'completed', progress: 100 });

    expect(nextSpy).toHaveBeenCalledTimes(2);
    expect(completeSpy).toHaveBeenCalledTimes(1);
    expect(sub.closed).toBe(true);
    expect(service.realtimeService.watchJob).not.toHaveBeenCalled();
  });

  it('falls back to the multiplexed stream when the per-job SSE endpoint errors', async () => {
    const service = Object.create(JobService.prototype) as any;
    const updates$ = new Subject<JobUpdate>();
    service.realtimeService = {
      watchJob: vi.fn(() =>
        updates$.pipe(takeWhile((job) => job.status !== 'completed' && job.status !== 'failed', true)),
      ),
    };
    service.sseService = {
      connect: vi.fn(() => throwError(() => new Error('direct stream failed'))),
    };

    const nextSpy = vi.fn();
    const completeSpy = vi.fn();
    const sub = service.watchJob('job-2').subscribe({
      next: nextSpy,
      complete: completeSpy,
    });

    updates$.next({ jobId: 'job-2', status: 'processing', progress: 25 });
    updates$.next({
      jobId: 'job-2',
      status: 'completed',
      progress: 100,
      result: { isValid: true },
    });

    const job = nextSpy.mock.calls.at(-1)?.[0] as AsyncJob;

    expect(service.sseService.connect).toHaveBeenCalledWith('/api/async-jobs/status/job-2/');
    expect(service.realtimeService.watchJob).toHaveBeenCalledWith('job-2');
    expect(job.jobId).toBe('job-2');
    expect(job.result).toEqual({ isValid: true });
    expect(completeSpy).toHaveBeenCalledTimes(1);
    expect(sub.closed).toBe(true);
  });
});
