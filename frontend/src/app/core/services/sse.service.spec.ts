import { NgZone } from '@angular/core';
import { firstValueFrom } from 'rxjs';
import { vi } from 'vitest';
import { AuthService } from './auth.service';
import { SseService } from './sse.service';

describe('SseService', () => {
  let sse: SseService;
  let mockAuth: any;
  const ngZoneMock: any = { run: (fn: any) => fn() };
  const createSseResponse = (chunks: string[], status = 200) => {
    const encoder = new TextEncoder();
    let index = 0;
    return {
      ok: status >= 200 && status < 300,
      status,
      body: {
        getReader: () => ({
          read: vi.fn(async () => {
            if (index >= chunks.length) return { done: true, value: undefined };
            const value = encoder.encode(chunks[index++]);
            return { done: false, value };
          }),
        }),
      },
    } as any;
  };

  beforeEach(() => {
    mockAuth = {
      isTokenExpired: vi.fn().mockReturnValue(false),
      logout: vi.fn(),
      getToken: vi.fn().mockReturnValue('jwt-token'),
      isMockEnabled: vi.fn().mockReturnValue(false),
    };
    (globalThis as any).fetch = vi.fn();
    sse = new SseService(ngZoneMock as NgZone, mockAuth as AuthService);
  });

  it('rejects connection if token is expired and triggers logout', () => {
    mockAuth.isTokenExpired.mockReturnValue(true);

    return new Promise<void>((resolve) => {
      sse.connect('/sse').subscribe({
        next: () => {
          throw new Error('should not emit next');
        },
        error: (err) => {
          expect(mockAuth.logout).toHaveBeenCalled();
          expect(err).toBeInstanceOf(Error);
          resolve();
        },
      });
    });
  });

  it('connects and emits messages when token is valid', () => {
    mockAuth.isTokenExpired.mockReturnValue(false);
    (globalThis.fetch as any).mockResolvedValue(
      createSseResponse(['data: {"message":"one"}\n\n', 'data: {"message":"two"}\n\n']),
    );

    return new Promise<void>((resolve) => {
      const received: any[] = [];
      const sub = sse.connect('/sse').subscribe({
        next: (v) => {
          received.push(v);
          if (received.length === 2) {
            sub.unsubscribe();
            resolve();
          }
        },
        error: (e) => {
          throw new Error(`unexpected error ${e}`);
        },
      });
    });
  });

  it('sends Authorization header when token is available', async () => {
    (globalThis.fetch as any).mockResolvedValue(createSseResponse([': keepalive\n\n']));

    const sub = sse.connect('/sse').subscribe({ next: () => {}, error: () => {} });
    await Promise.resolve();

    expect(globalThis.fetch).toHaveBeenCalled();
    const [, options] = (globalThis.fetch as any).mock.calls[0];
    expect(options.headers.get('Authorization')).toBe('Bearer jwt-token');
    sub.unsubscribe();
  });

  it('parses SSE event/id frames via connectMessages', async () => {
    (globalThis.fetch as any).mockResolvedValue(
      createSseResponse(['id: 1710000000000-0\nevent: job_update\ndata: {"status":"processing"}\n\n']),
    );

    const message = await firstValueFrom(sse.connectMessages<{ status: string }>('/sse'));
    expect(message.event).toBe('job_update');
    expect(message.id).toBe('1710000000000-0');
    expect(message.data.status).toBe('processing');
  });

  it('sends Last-Event-ID header on reconnect for the same URL', async () => {
    (globalThis.fetch as any)
      .mockResolvedValueOnce(createSseResponse(['id: 42-0\ndata: {"step":"one"}\n\n']))
      .mockResolvedValueOnce(createSseResponse(['data: {"step":"two"}\n\n']));

    await firstValueFrom(sse.connectMessages<{ step: string }>('/sse'));
    await firstValueFrom(sse.connectMessages<{ step: string }>('/sse'));

    const [, firstOptions] = (globalThis.fetch as any).mock.calls[0];
    const [, secondOptions] = (globalThis.fetch as any).mock.calls[1];

    expect(firstOptions.headers.get('Last-Event-ID')).toBeNull();
    expect(secondOptions.headers.get('Last-Event-ID')).toBe('42-0');
  });

  it('does not send Last-Event-ID when replay cursor is disabled', async () => {
    (globalThis.fetch as any)
      .mockResolvedValueOnce(createSseResponse(['id: 99-0\ndata: {"step":"one"}\n\n']))
      .mockResolvedValueOnce(createSseResponse(['data: {"step":"two"}\n\n']));

    await firstValueFrom(sse.connectMessages<{ step: string }>('/sse-no-replay', { useReplayCursor: false }));
    await firstValueFrom(sse.connectMessages<{ step: string }>('/sse-no-replay', { useReplayCursor: false }));

    const [, firstOptions] = (globalThis.fetch as any).mock.calls[0];
    const [, secondOptions] = (globalThis.fetch as any).mock.calls[1];

    expect(firstOptions.headers.get('Last-Event-ID')).toBeNull();
    expect(secondOptions.headers.get('Last-Event-ID')).toBeNull();
  });
});
