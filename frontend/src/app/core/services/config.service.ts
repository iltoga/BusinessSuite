import { HttpBackend, HttpClient } from '@angular/common/http';
import { computed, inject, Injectable, signal } from '@angular/core';
import { catchError, firstValueFrom, of, tap } from 'rxjs';

import { AppConfig, DEFAULT_APP_CONFIG } from '@/core/config/app.config';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private _config = signal<AppConfig>(DEFAULT_APP_CONFIG);
  private readonly http = new HttpClient(inject(HttpBackend));

  // Publicly expose as a read-only signal
  readonly config = computed(() => this._config());

  constructor() {}

  loadConfig() {
    // Seed from server-injected config first (SSR or production inject),
    // but still fetch backend app-config so auth flags stay synchronized.
    const injectedConfig = (window as any).APP_CONFIG;
    if (injectedConfig) {
      this._config.set({ ...DEFAULT_APP_CONFIG, ...injectedConfig });
    }

    return firstValueFrom(
      this.http.get<AppConfig>('/api/app-config/').pipe(
        tap((data) => {
          this._config.set({ ...DEFAULT_APP_CONFIG, ...(injectedConfig || {}), ...data });
        }),
        catchError((error) => {
          console.warn('[ConfigService] Failed to load /api/app-config/.', error);
          if (!injectedConfig) {
            this._config.set(DEFAULT_APP_CONFIG);
          }

          return of(this._config());
        }),
      ),
    );
  }

  get settings() {
    return this._config();
  }
}
