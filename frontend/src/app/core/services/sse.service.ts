import { Injectable, NgZone } from '@angular/core';
import { Observable } from 'rxjs';

export interface SseOptions {
  withCredentials?: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class SseService {
  constructor(private zone: NgZone) {}

  connect<T>(url: string, options: SseOptions = {}): Observable<T> {
    const withCredentials = options.withCredentials ?? true;

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
