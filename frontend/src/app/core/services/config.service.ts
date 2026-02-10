import { HttpBackend, HttpClient } from '@angular/common/http';
import { computed, Injectable, signal } from '@angular/core';
import { catchError, firstValueFrom, of, tap } from 'rxjs';

import { AppConfig, DEFAULT_APP_CONFIG } from '@/core/config/app.config';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private _config = signal<AppConfig>(DEFAULT_APP_CONFIG);
  private http: HttpClient;

  // Publicly expose as a read-only signal
  readonly config = computed(() => this._config());

  constructor(handler: HttpBackend) {
    this.http = new HttpClient(handler);
  }

  loadConfig() {
    // Check for server-injected config first (SSR or production inject)
    const injectedConfig = (window as any).APP_CONFIG;
    if (injectedConfig) {
      this._config.set({ ...DEFAULT_APP_CONFIG, ...injectedConfig });
      return Promise.resolve(this._config());
    }

    return firstValueFrom(
      this.http.get<AppConfig>('/api/app-config/').pipe(
        tap((data) => {
          this._config.set({ ...DEFAULT_APP_CONFIG, ...data });
        }),
        catchError((error) => {
          console.warn('[ConfigService] Failed to load /api/app-config/.', error);
          this._config.set(DEFAULT_APP_CONFIG);

          return of(this._config());
        }),
      ),
    );
  }

  get settings() {
    return this._config();
  }
}
