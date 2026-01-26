import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { catchError, firstValueFrom, of, tap } from 'rxjs';

import { AppConfig, DEFAULT_APP_CONFIG } from '@/core/config/app.config';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private config: AppConfig = DEFAULT_APP_CONFIG;

  constructor(private http: HttpClient) {}

  loadConfig() {
    return firstValueFrom(
      this.http.get<AppConfig>('/assets/config.json').pipe(
        tap((data) => {
          this.config = { ...DEFAULT_APP_CONFIG, ...data };
        }),
        catchError((error) => {
          console.warn('[ConfigService] Failed to load /assets/config.json.', error);
          this.config = DEFAULT_APP_CONFIG;
          return of(this.config);
        }),
      ),
    );
  }

  get settings() {
    return this.config;
  }
}
