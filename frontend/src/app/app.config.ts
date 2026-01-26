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
import { ConfigService } from '@/core/services/config.service';
import { ThemeService } from '@/core/services/theme.service';
import { provideZard } from '@/shared/core/provider/providezard';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { routes } from './app.routes';

import { provideServiceWorker } from '@angular/service-worker';
import { MOCK_AUTH_ENABLED } from './core/config/mock-auth.token';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideZard(),
    provideClientHydration(withEventReplay()),

    // Load runtime config then initialize theme
    provideAppInitializer(() => {
      const configService = inject(ConfigService);
      const themeService = inject(ThemeService);
      const platformId = inject(PLATFORM_ID);

      if (!isPlatformBrowser(platformId)) {
        return Promise.resolve();
      }

      return configService.loadConfig().then(() => {
        themeService.initializeTheme(configService.settings.theme);
      });
    }),

    // Mocked authentication (toggle in src/assets/config.json)
    {
      provide: MOCK_AUTH_ENABLED,
      useFactory: () => {
        const configService = inject(ConfigService);
        return configService.settings.mockAuthEnabled;
      },
    },
    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
