import { of, Subject, throwError } from 'rxjs';
import { describe, expect, it, vi } from 'vitest';

import {
  mapJobUpdateToAsyncJob,
  RealtimeNotificationService,
  type RealtimeJobUpdate,
} from './realtime-notification.service';
import { type SseMessage } from './sse.service';

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

describe('RealtimeNotificationService.watchJob', () => {
  it('completes when the tracked job reaches a terminal state', () => {
    const service = Object.create(RealtimeNotificationService.prototype) as any;
    const events$ = new Subject<SseMessage<unknown>>();
    service._events$ = events$.asObservable();

    const nextSpy = vi.fn();
    const completeSpy = vi.fn();
    const sub = service.watchJob('job-1').subscribe({
      next: nextSpy,
      complete: completeSpy,
    });

    events$.next({
      event: 'job_update',
      id: '1',
      data: { jobId: 'job-1', status: 'processing', progress: 25 },
    });
    expect(completeSpy).not.toHaveBeenCalled();

    events$.next({
      event: 'job_update',
      id: '2',
      data: { jobId: 'job-1', status: 'completed', progress: 100 },
    });

    expect(nextSpy).toHaveBeenCalledTimes(2);
    expect(completeSpy).toHaveBeenCalledTimes(1);
    expect(sub.closed).toBe(true);
  });

  it('reconnects the shared realtime stream after clean completion', async () => {
    vi.useFakeTimers();

    const service = Object.create(RealtimeNotificationService.prototype) as any;
    service._events$ = null;
    service.sseService = {
      connectMessages: vi
        .fn()
        .mockReturnValueOnce(
          of({
            event: 'job_update',
            id: '1',
            data: { jobId: 'job-9', status: 'processing', progress: 25 },
          }),
        )
        .mockReturnValueOnce(
          of({
            event: 'job_update',
            id: '2',
            data: { jobId: 'job-9', status: 'completed', progress: 100 },
          }),
        ),
    };

    const nextSpy = vi.fn();
    const completeSpy = vi.fn();

    service.watchJob('job-9').subscribe({
      next: nextSpy,
      complete: completeSpy,
    });

    await vi.runAllTimersAsync();

    expect(service.sseService.connectMessages).toHaveBeenCalledTimes(2);
    expect(service.sseService.connectMessages).toHaveBeenNthCalledWith(
      1,
      '/api/core/realtime/stream/',
      {
        maxConnectionDurationMs: 55_000,
      },
    );
    expect(nextSpy).toHaveBeenCalledTimes(2);
    expect(nextSpy.mock.calls[0]?.[0]).toMatchObject({
      jobId: 'job-9',
      status: 'processing',
      progress: 25,
    });
    expect(nextSpy.mock.calls[1]?.[0]).toMatchObject({
      jobId: 'job-9',
      status: 'completed',
      progress: 100,
    });
    expect(completeSpy).toHaveBeenCalledTimes(1);
  });

  it('resets the shared realtime stream after an initial connection error', () => {
    const service = Object.create(RealtimeNotificationService.prototype) as any;
    service._events$ = null;
    service.sseService = {
      connectMessages: vi
        .fn()
        .mockReturnValueOnce(throwError(() => new Error('stream boot failed')))
        .mockReturnValueOnce(
          of({
            event: 'job_update',
            id: '3',
            data: { jobId: 'job-reset', status: 'processing', progress: 5 },
          }),
        ),
    };

    const firstErrorSpy = vi.fn();
    service.watchAll().subscribe({
      error: firstErrorSpy,
    });

    expect(firstErrorSpy).toHaveBeenCalledTimes(1);

    const nextSpy = vi.fn();
    const sub = service.watchAll().subscribe({
      next: nextSpy,
    });

    expect(service.sseService.connectMessages).toHaveBeenCalledTimes(2);
    expect(service.sseService.connectMessages).toHaveBeenNthCalledWith(
      2,
      '/api/core/realtime/stream/',
      {
        maxConnectionDurationMs: 55_000,
      },
    );
    expect(nextSpy).toHaveBeenCalledWith({
      event: 'job_update',
      id: '3',
      data: { jobId: 'job-reset', status: 'processing', progress: 5 },
    });

    sub.unsubscribe();
  });
});
