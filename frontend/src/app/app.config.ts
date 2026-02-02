import { isPlatformBrowser } from '@angular/common';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  isDevMode,
  PLATFORM_ID,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
} from '@angular/core';
import { provideRouter } from '@angular/router';

import { authInterceptor } from '@/core/interceptors/auth.interceptor';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { ThemeService } from '@/core/services/theme.service';
import { provideZard } from '@/shared/core/provider/providezard';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { routes } from './app.routes';

import { provideApi } from '@/core/api';
import { provideServiceWorker } from '@angular/service-worker';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideApi(''),
    provideZard(),
    provideClientHydration(withEventReplay()),

    // Load runtime config then initialize theme and auth
    provideAppInitializer(() => {
      const configService = inject(ConfigService);
      const themeService = inject(ThemeService);
      const authService = inject(AuthService);
      const platformId = inject(PLATFORM_ID);

      if (!isPlatformBrowser(platformId)) {
        return Promise.resolve();
      }

      return configService.loadConfig().then(() => {
        themeService.initializeTheme(configService.settings.theme);
        authService.initMockAuth();

        // Ensure SPA-only loads also reveal the correct brand once config is loaded
        try {
          document.documentElement.classList.add('app-brand-ready');
        } catch (e) {
          /* ignore on non-browser platforms */
        }
      });
    }),

    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
