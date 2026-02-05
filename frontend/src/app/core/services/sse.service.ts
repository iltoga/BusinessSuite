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
      const source = new EventSource(url, { withCredentials });

      source.onmessage = (event) => {
        this.zone.run(() => {
          try {
            subscriber.next(JSON.parse(event.data) as T);
          } catch (error) {
            subscriber.error(error);
          }
        });
      };

      source.onerror = (error) => {
        this.zone.run(() => subscriber.error(error));
        source.close();
      };

      return () => source.close();
    });
  }
}
