import { Injectable, NgZone } from '@angular/core';
import { map, Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface SseOptions {
  withCredentials?: boolean;
  useReplayCursor?: boolean;
  maxConnectionDurationMs?: number;
}

export interface SseMessage<T> {
  event: string;
  data: T;
  id?: string;
}

@Injectable({
  providedIn: 'root',
})
export class SseService {
  private readonly lastEventIds = new Map<string, string>();

  constructor(
    private zone: NgZone,
    private authService: AuthService,
  ) {}

  connect<T>(url: string, options: SseOptions = {}): Observable<T> {
    return this.connectMessages<T>(url, options).pipe(map((message) => message.data));
  }

  connectMessages<T>(url: string, options: SseOptions = {}): Observable<SseMessage<T>> {
    const withCredentials = options.withCredentials ?? true;
    const useReplayCursor = options.useReplayCursor ?? true;
    const maxConnectionDurationMs =
      typeof options.maxConnectionDurationMs === 'number' && options.maxConnectionDurationMs > 0
        ? options.maxConnectionDurationMs
        : null;

    // If token is expired, force logout and return an observable error immediately
    if (this.authService.isTokenExpired()) {
      this.authService.logout();
      return new Observable<SseMessage<T>>((subscriber) =>
        subscriber.error(new Error('Token expired')),
      );
    }

    return new Observable<SseMessage<T>>((subscriber) => {
      const controller = new AbortController();
      let shouldCompleteAfterAbort = false;
      let rotationTimeoutId: ReturnType<typeof setTimeout> | null = null;
      let isSettled = false;

      const clearRotationTimeout = () => {
        if (rotationTimeoutId === null) {
          return;
        }

        clearTimeout(rotationTimeoutId);
        rotationTimeoutId = null;
      };

      const completeSubscriber = () => {
        if (isSettled) {
          return;
        }

        isSettled = true;
        clearRotationTimeout();
        this.zone.run(() => subscriber.complete());
      };

      const errorSubscriber = (error: unknown) => {
        if (isSettled) {
          return;
        }

        isSettled = true;
        clearRotationTimeout();
        this.zone.run(() => subscriber.error(error));
      };

      const streamSse = async () => {
        try {
          if (maxConnectionDurationMs !== null) {
            rotationTimeoutId = setTimeout(() => {
              shouldCompleteAfterAbort = true;
              controller.abort();
            }, maxConnectionDurationMs);
          }

          const headers = new Headers({ Accept: 'text/event-stream' });
          const token =
            this.authService.getToken() ?? (this.authService.isMockEnabled() ? 'mock-token' : null);
          if (token) {
            headers.set('Authorization', `Bearer ${token}`);
          }
          if (useReplayCursor) {
            const lastEventId = this.lastEventIds.get(url);
            if (lastEventId) {
              headers.set('Last-Event-ID', lastEventId);
            }
          }

          const response = await fetch(url, {
            method: 'GET',
            headers,
            credentials: withCredentials ? 'include' : 'same-origin',
            cache: 'no-store',
            signal: controller.signal,
          });

          if (!response.ok) {
            throw new Error(`SSE request failed (${response.status})`);
          }
          if (!response.body) {
            throw new Error('SSE stream body is unavailable');
          }

          const reader = response.body.getReader();
          const decoder = new TextDecoder();
          let buffer = '';

          while (true) {
            const { done, value } = await reader.read();
            if (done) break;

            buffer += decoder.decode(value, { stream: true });
            buffer = buffer.replace(/\r\n/g, '\n');

            let frameBoundary = buffer.indexOf('\n\n');
            while (frameBoundary !== -1) {
              const frame = buffer.slice(0, frameBoundary);
              buffer = buffer.slice(frameBoundary + 2);
              this.handleFrame<T>(url, frame, subscriber);
              frameBoundary = buffer.indexOf('\n\n');
            }
          }

          if (buffer.trim().length > 0) {
            this.handleFrame<T>(url, buffer, subscriber);
          }

          completeSubscriber();
        } catch (error) {
          if (controller.signal.aborted) {
            if (shouldCompleteAfterAbort) {
              shouldCompleteAfterAbort = false;
              completeSubscriber();
            }
            return;
          }

          errorSubscriber(error);
        }
      };

      void streamSse();
      return () => {
        clearRotationTimeout();
        controller.abort();
      };
    });
  }

  private handleFrame<T>(
    url: string,
    frame: string,
    subscriber: { next(value: SseMessage<T>): void; error(err: unknown): void },
  ): void {
    const lines = frame.split('\n');
    const dataLines: string[] = [];
    let eventType = 'message';
    let eventId: string | undefined;

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (!line || line.startsWith(':')) {
        continue;
      }
      if (line.startsWith('event:')) {
        eventType = line.slice(6).trim() || 'message';
        continue;
      }
      if (line.startsWith('id:')) {
        const parsedId = line.slice(3).trim();
        if (parsedId) {
          eventId = parsedId;
          this.lastEventIds.set(url, parsedId);
        }
        continue;
      }
      if (line.startsWith('data:')) {
        dataLines.push(line.slice(5).trimStart());
      }
    }

    if (dataLines.length === 0) return;

    const payload = dataLines.join('\n');
    this.zone.run(() => {
      try {
        subscriber.next({
          event: eventType,
          data: JSON.parse(payload) as T,
          id: eventId,
        });
      } catch (error) {
        subscriber.error(error);
      }
    });
  }
}
