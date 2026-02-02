import { HttpBackend, HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { catchError, firstValueFrom, of, tap } from 'rxjs';

import { AppConfig, DEFAULT_APP_CONFIG } from '@/core/config/app.config';

@Injectable({ providedIn: 'root' })
export class ConfigService {
  private config: AppConfig = DEFAULT_APP_CONFIG;
  private http: HttpClient;

  constructor(handler: HttpBackend) {
    this.http = new HttpClient(handler);
  }

  loadConfig() {
    return firstValueFrom(
      this.http.get<AppConfig>('/assets/config.json').pipe(
        tap((data) => {
          this.config = { ...DEFAULT_APP_CONFIG, ...data };

          // Merge any server-injected branding (SSR). window.APP_BRAND is injected by server.ts
          const brand = (window as any).APP_BRAND;
          if (brand) {
            const normal = brand.logo ? String(brand.logo).replace(/^\/assets\//, '') : undefined;
            const inverted = brand.logoInverted
              ? String(brand.logoInverted).replace(/^\/assets\//, '')
              : undefined;
            this.config = {
              ...this.config,
              ...(normal ? { logoFilename: normal } : {}),
              ...(inverted ? { logoInvertedFilename: inverted } : {}),
            };
          }
        }),
        catchError((error) => {
          console.warn('[ConfigService] Failed to load /assets/config.json.', error);
          this.config = DEFAULT_APP_CONFIG;

          // Still allow server-injected branding to be used when assets config is missing
          const brand = (window as any).APP_BRAND;
          if (brand) {
            const normal = brand.logo ? String(brand.logo).replace(/^\/assets\//, '') : undefined;
            const inverted = brand.logoInverted
              ? String(brand.logoInverted).replace(/^\/assets\//, '')
              : undefined;
            this.config = {
              ...this.config,
              ...(normal ? { logoFilename: normal } : {}),
              ...(inverted ? { logoInvertedFilename: inverted } : {}),
            };
          }

          return of(this.config);
        }),
      ),
    );
  }

  get settings() {
    return this.config;
  }
}
