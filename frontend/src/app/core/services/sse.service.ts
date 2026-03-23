/**
 * SseService — Angular service for consuming Server-Sent Events (SSE) streams.
 *
 * ## Overview
 * Wraps the browser's `fetch` API (not `EventSource`) so that the
 * `Authorization: Bearer <token>` header can be sent on first connect.  The
 * stream is read as a `ReadableStream<Uint8Array>` and parsed line-by-line
 * using the SSE wire format (`event:`, `data:`, `id:` fields).
 *
 * ## `connect<T>(url, options)` vs `connectMessages<T>(url, options)`
 * - `connect()` is a thin wrapper returning only `message.data`.
 * - `connectMessages()` returns the full `SseMessage<T>` envelope
 *   (`event`, `data`, `id`) and is needed when you must react to named
 *   event types.
 *
 * ## Reconnection strategy (cursor replay)
 * When `useReplayCursor: true` (default) the service stores the last
 * `id:` field value per URL in `lastEventIds: Map<string, string>`.  On
 * reconnect the stored id is sent as the `Last-Event-ID` request header so
 * the server can replay missed events.
 *
 * ## Circuit-breaker (`maxConnectionDurationMs`)
 * When `maxConnectionDurationMs` is set, a `setTimeout` fires after that
 * duration, calls `AbortController.abort()`, and sets
 * `shouldCompleteAfterAbort = true` so the `AbortError` is treated as a
 * clean `complete()` rather than an `error()`.  Callers can restart the
 * stream externally (e.g. via a `retry()` or `switchMap` in the component)
 * to implement long-lived rotation.
 *
 * ## `AbortController` cleanup contract
 * Each `Observable` subscription owns one `AbortController`.  The controller
 * is aborted (and the fetch connection closed) when:
 * - The `maxConnectionDurationMs` timer fires.
 * - The subscriber calls `unsubscribe()` (teardown logic).
 * - The server closes the stream (fetch body resolves to `done`).
 * - An error occurs before the stream opens.
 *
 * ## Token expiry guard
 * Before opening a connection, `authService.isTokenExpired()` is checked.
 * If the token is expired, `authService.logout()` is called and the
 * Observable immediately errors with `new Error('Token expired')`.
 */
import { Injectable, NgZone } from '@angular/core';
import { map, Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import {
  createRequestMetadata,
  requestMetadataHeaders,
  type RequestMetadata,
} from '@/core/utils/request-metadata';

export interface SseOptions {
  withCredentials?: boolean;
  useReplayCursor?: boolean;
  maxConnectionDurationMs?: number;
  requestMetadata?: RequestMetadata | null;
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
    const requestMetadata = options.requestMetadata ?? createRequestMetadata();
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
      let streamOpened = false;
      const lastEventIdAtOpen = useReplayCursor ? this.lastEventIds.get(url) ?? null : null;

      if (lastEventIdAtOpen) {
        console.info('[SseService] Reconnecting SSE stream', {
          url,
          requestId: requestMetadata.requestId,
          lastEventId: lastEventIdAtOpen,
        });
      } else {
        console.info('[SseService] Opening SSE stream', {
          url,
          requestId: requestMetadata.requestId,
        });
      }

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

          const headers = new Headers({
            Accept: 'text/event-stream',
            ...requestMetadataHeaders(requestMetadata),
          });
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
            console.warn('[SseService] SSE request failed', { url, status: response.status });
            throw new Error(`SSE request failed (${response.status})`);
          }
          if (!response.body) {
            console.warn('[SseService] SSE stream body is unavailable', { url });
            throw new Error('SSE stream body is unavailable');
          }

          streamOpened = true;
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

          console.info('[SseService] SSE stream completed', {
            url,
            requestId: requestMetadata.requestId,
            lastEventId: this.lastEventIds.get(url) ?? null,
          });
          completeSubscriber();
        } catch (error) {
          if (controller.signal.aborted) {
            if (shouldCompleteAfterAbort) {
              shouldCompleteAfterAbort = false;
              console.info('[SseService] SSE stream rotated or aborted', {
                url,
                requestId: requestMetadata.requestId,
                lastEventId: this.lastEventIds.get(url) ?? null,
              });
              completeSubscriber();
            }
            return;
          }

          if (streamOpened) {
            console.info('[SseService] SSE stream disconnected', {
              url,
              requestId: requestMetadata.requestId,
              error: this.describeError(error),
            });
            completeSubscriber();
            return;
          }

          console.error('[SseService] SSE stream error', {
            url,
            requestId: requestMetadata.requestId,
            error: this.describeError(error),
          });
          errorSubscriber(error);
        }
      };

      void streamSse();
      return () => {
        clearRotationTimeout();
        if (!isSettled) {
          console.info('[SseService] SSE stream unsubscribed', {
            url,
            requestId: requestMetadata.requestId,
            lastEventId: this.lastEventIds.get(url) ?? null,
          });
        }
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
        console.error('[SseService] Failed to parse SSE payload', { url, error });
        subscriber.error(error);
      }
    });
  }

  private describeError(error: unknown): { name?: string; message?: string } {
    if (error instanceof Error) {
      return {
        name: error.name,
        message: error.message,
      };
    }

    return {
      message: String(error ?? 'Unknown SSE error'),
    };
  }
}
