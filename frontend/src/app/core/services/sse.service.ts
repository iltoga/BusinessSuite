import { Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface SseOptions {
  withCredentials?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class SseService {
  constructor(
    private zone: NgZone,
    private authService: AuthService,
  ) {}

  connect<T>(url: string, options: SseOptions = {}): Observable<T> {
    const withCredentials = options.withCredentials ?? true;

    // If token is expired, force logout and return an observable error immediately
    if (this.authService.isTokenExpired()) {
      this.authService.logout();
      return new Observable<T>((subscriber) => subscriber.error(new Error('Token expired')));
    }

    return new Observable<T>((subscriber) => {
      const controller = new AbortController();

      const streamSse = async () => {
        try {
          const headers = new Headers({ Accept: 'text/event-stream' });
          const token = this.authService.getToken() ?? (this.authService.isMockEnabled() ? 'mock-token' : null);
          if (token) {
            headers.set('Authorization', `Bearer ${token}`);
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
              this.handleFrame<T>(frame, subscriber);
              frameBoundary = buffer.indexOf('\n\n');
            }
          }

          if (buffer.trim().length > 0) {
            this.handleFrame<T>(buffer, subscriber);
          }

          this.zone.run(() => subscriber.complete());
        } catch (error) {
          if (controller.signal.aborted) return;
          this.zone.run(() => subscriber.error(error));
        }
      };

      void streamSse();
      return () => controller.abort();
    });
  }

  private handleFrame<T>(frame: string, subscriber: { next(value: T): void; error(err: unknown): void }): void {
    const lines = frame.split('\n');
    const dataLines: string[] = [];

    for (const rawLine of lines) {
      const line = rawLine.trimEnd();
      if (!line || line.startsWith(':')) {
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
        subscriber.next(JSON.parse(payload) as T);
      } catch (error) {
        subscriber.error(error);
      }
    });
  }
}
