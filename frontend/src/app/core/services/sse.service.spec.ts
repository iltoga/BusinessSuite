import { NgZone } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { vi } from 'vitest';
import { AuthService } from './auth.service';
import { SseService } from './sse.service';

// Simple mock for EventSource so we can simulate messages and errors
class MockEventSource {
  public onmessage: ((e: any) => void) | null = null;
  public onerror: ((e: any) => void) | null = null;
  public closed = false;
  constructor(
    public url: string,
    _opts?: any,
  ) {
    // store instance so tests can access it
    (MockEventSource as any).latest = this;
  }
  close() {
    this.closed = true;
  }
  emitMessage(payload: any) {
    if (this.onmessage) this.onmessage({ data: JSON.stringify(payload) });
  }
  emitError(err: any) {
    if (this.onerror) this.onerror(err);
  }
}

describe('SseService', () => {
  let sse: SseService;
  let mockAuth: any;
  const ngZoneMock: any = { run: (fn: any) => fn() };

  beforeEach(() => {
    mockAuth = { isTokenExpired: vi.fn().mockReturnValue(false), logout: vi.fn() };

    // Replace global EventSource
    (globalThis as any).EventSource = MockEventSource;

    TestBed.configureTestingModule({
      providers: [
        SseService,
        { provide: AuthService, useValue: mockAuth },
        { provide: NgZone, useValue: ngZoneMock },
      ],
    });

    sse = TestBed.inject(SseService);
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

      // Access the created MockEventSource and emit messages
      const es = (MockEventSource as any).latest as MockEventSource;
      expect(es).toBeDefined();

      es.emitMessage({ message: 'one' });
      es.emitMessage({ message: 'two' });
    });
  });
});
