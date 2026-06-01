import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { of } from 'rxjs';
import { vi } from 'vitest';

import { OcrService } from './ocr.service';
import { SseService } from './sse.service';

describe('OcrService passport OCR', () => {
  let service: OcrService;
  let httpMock: HttpTestingController;
  const sseServiceMock = {
    connect: vi.fn(),
  };

  beforeEach(() => {
    sseServiceMock.connect.mockReset();

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [OcrService, { provide: SseService, useValue: sseServiceMock }],
    });

    service = TestBed.inject(OcrService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
  });

  it('sends OCR-only mode explicitly', () => {
    const file = new File(['passport'], 'passport.png', { type: 'image/png' });
    let responseJobId: string | undefined;

    service.startPassportOcr(file, { useAi: false }).subscribe((response) => {
      responseJobId = response.jobId;
    });

    const req = httpMock.expectOne('/api/ocr/check/');
    const body = req.request.body as FormData;

    expect(req.request.method).toBe('POST');
    expect(body.get('file')).toBe(file);
    expect(body.get('doc_type')).toBe('passport');
    expect(body.get('use_ai')).toBe('false');

    req.flush({ jobId: 'job-ocr-only', status: 'queued', progress: 0 });

    expect(responseJobId).toBe('job-ocr-only');
  });

  it('sends AI mode explicitly', () => {
    const file = new File(['passport'], 'passport.png', { type: 'image/png' });

    service.startPassportOcr(file, { useAi: true }).subscribe();

    const req = httpMock.expectOne('/api/ocr/check/');
    const body = req.request.body as FormData;

    expect(req.request.method).toBe('POST');
    expect(body.get('use_ai')).toBe('true');

    req.flush({ jobId: 'job-ai', status: 'queued', progress: 0 });
  });

  it('watches passport jobs through the generic async job SSE endpoint', () => {
    sseServiceMock.connect.mockReturnValue(
      of({
        jobId: 'job-ai',
        status: 'completed',
        progress: 100,
        extractionMode: 'ai',
        result: { mrzData: { number: 'X123' } },
      }),
    );

    let result: unknown;
    service.watchPassportOcrJob('job-ai', '/api/ocr/stream/job-ai/').subscribe((value) => {
      result = value;
    });

    expect(sseServiceMock.connect).toHaveBeenCalledWith('/api/async-jobs/status/job-ai/', {
      maxConnectionDurationMs: 55_000,
    });
    expect(result).toMatchObject({
      jobId: 'job-ai',
      status: 'completed',
      progress: 100,
      extractionMode: 'ai',
      mrzData: { number: 'X123' },
    });
  });

  it('reconnects passport job tracking when the stream completes before terminal state', async () => {
    vi.useFakeTimers();

    sseServiceMock.connect
      .mockReturnValueOnce(
        of({
          jobId: 'job-reconnect',
          status: 'processing',
          progress: 25,
          extractionMode: 'ai',
        }),
      )
      .mockReturnValueOnce(
        of({
          jobId: 'job-reconnect',
          status: 'completed',
          progress: 100,
          extractionMode: 'ai',
          result: { mrzData: { number: 'Y987' } },
        }),
      );

    const received: Array<unknown> = [];

    service.watchPassportOcrJob('job-reconnect').subscribe((value) => {
      received.push(value);
    });

    await vi.runAllTimersAsync();

    expect(sseServiceMock.connect).toHaveBeenCalledTimes(2);
    expect(sseServiceMock.connect).toHaveBeenNthCalledWith(
      1,
      '/api/async-jobs/status/job-reconnect/',
      {
        maxConnectionDurationMs: 55_000,
      },
    );
    expect(received).toHaveLength(2);
    expect(received[0]).toMatchObject({
      jobId: 'job-reconnect',
      status: 'processing',
      progress: 25,
    });
    expect(received[1]).toMatchObject({
      jobId: 'job-reconnect',
      status: 'completed',
      progress: 100,
      mrzData: { number: 'Y987' },
    });
  });
});
