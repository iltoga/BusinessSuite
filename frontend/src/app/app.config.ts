import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  APP_INITIALIZER,
  ApplicationConfig,
  provideBrowserGlobalErrorListeners, isDevMode,
} from '@angular/core';
import { provideRouter } from '@angular/router';

import { authInterceptor } from '@/core/interceptors/auth.interceptor';
import { ThemeService } from '@/core/services/theme.service';
import { provideZard } from '@/shared/core/provider/providezard';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { routes } from './app.routes';

import { APP_CONFIG } from './core/config/app.config';
import { MOCK_AUTH_ENABLED } from './core/config/mock-auth.token';
import { provideServiceWorker } from '@angular/service-worker';

/**
 * Theme initialization factory
 * Applies the configured theme on app startup
 */
function initializeTheme(themeService: ThemeService) {
  return () => {
    themeService.initializeTheme(APP_CONFIG.theme);
  };
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideZard(),
    provideClientHydration(withEventReplay()),

    // Initialize theme on app startup
    {
      provide: APP_INITIALIZER,
      useFactory: initializeTheme,
      deps: [ThemeService],
      multi: true,
    },

    // Mocked authentication (toggle in src/app/core/config/app.config.ts)
    {
      provide: MOCK_AUTH_ENABLED,
      useValue: APP_CONFIG.mockAuthEnabled,
    }, provideServiceWorker('ngsw-worker.js', {
            enabled: !isDevMode(),
            registrationStrategy: 'registerWhenStable:30000'
          }),
  ],
};
