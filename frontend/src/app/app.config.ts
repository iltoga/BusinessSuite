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
import { Title } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

import { UserSettingsApiService } from '@/core/api/user-settings.service';
import { authInterceptor } from '@/core/interceptors/auth.interceptor';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { LoggerService } from '@/core/services/logger.service';
import { ThemeService } from '@/core/services/theme.service';
import { provideZard } from '@/shared/core/provider/providezard';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { firstValueFrom } from 'rxjs';
import { routes } from './app.routes';

import { provideApi } from '@/core/api';
import { provideServiceWorker } from '@angular/service-worker';
import { ThemeName } from './core/theme.config';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideApi(''),
    provideZard(),
    provideCharts(withDefaultRegisterables()),
    provideClientHydration(withEventReplay()),

    // Load runtime config then initialize theme and auth
    provideAppInitializer(() => {
      const configService = inject(ConfigService);
      const themeService = inject(ThemeService);
      const authService = inject(AuthService);
      const loggerService = inject(LoggerService);
      const platformId = inject(PLATFORM_ID);
      const userSettingsApi = inject(UserSettingsApiService);

      // Initialize browser logging as early as possible
      loggerService.init();

      if (!isPlatformBrowser(platformId)) {
        return Promise.resolve();
      }

      return configService.loadConfig().then(() => {
        authService.initMockAuth();

        // If authenticated, attempt to fetch user settings and apply theme/darkMode from server
        const applyFromServer = async () => {
          try {
            if (authService.isAuthenticated()) {
              const settings = await firstValueFrom(userSettingsApi.getMe());
              themeService.initializeTheme(
                (settings.theme ?? configService.settings.theme) as ThemeName,
              );
              // Accept either snake_case or camelCase keys from server
              const serverDark = (settings as any)?.dark_mode ?? (settings as any)?.darkMode;
              themeService.setDarkMode(
                typeof serverDark === 'boolean' ? serverDark : themeService.isDarkMode(),
              );
            } else {
              // Not authenticated: fall back to config.json and localStorage
              themeService.initializeTheme(configService.settings.theme as ThemeName);
            }
          } catch (e) {
            // On any failure, fall back to config+localstorage
            themeService.initializeTheme(configService.settings.theme as ThemeName);
          }
        };

        // Run asynchronously so initialization doesn't block excessively
        applyFromServer();

        // Set browser tab title from config if available
        try {
          const titleSvc = inject(Title);
          const cfgTitle = (configService.settings as any).title;
          if (cfgTitle) {
            titleSvc.setTitle(String(cfgTitle));
          }
        } catch (e) {
          /* ignore if Title is not available on this platform */
        }

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
