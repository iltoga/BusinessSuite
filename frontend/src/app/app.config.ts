import { isPlatformBrowser } from '@angular/common';
import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import {
  ApplicationConfig,
  inject,
  isDevMode,
  PLATFORM_ID,
  provideAppInitializer,
  provideBrowserGlobalErrorListeners,
  provideZonelessChangeDetection,
} from '@angular/core';
import { Title } from '@angular/platform-browser';
import { provideRouter } from '@angular/router';

import { UserSettingsApiService } from '@/core/api/user-settings.service';
import { authInterceptor } from '@/core/interceptors/auth.interceptor';
import { cacheInterceptor } from '@/core/interceptors/cache.interceptor';
import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { LoggerService } from '@/core/services/logger.service';
import { ThemePreferencePayload, ThemeService } from '@/core/services/theme.service';
import { provideZard } from '@/shared/core/provider/providezard';
import {
  provideClientHydration,
  withEventReplay,
  withHttpTransferCacheOptions,
} from '@angular/platform-browser';
import { provideCharts, withDefaultRegisterables } from 'ng2-charts';
import { firstValueFrom, timeout } from 'rxjs';
import { routes } from './app.routes';

import { provideApi } from '@/core/api';
import { provideServiceWorker } from '@angular/service-worker';
import { ThemeName } from './core/theme.config';

type AppTitleSettings = {
  title?: string | null;
};

export type InitializeApplicationDeps = {
  configService: ConfigService;
  themeService: ThemeService;
  authService: AuthService;
  loggerService: LoggerService;
  userSettingsApi: UserSettingsApiService;
  titleService: Title;
  isBrowser: boolean;
};

/** Max time (ms) to wait for userSettingsApi.getMe() during init. */
const USER_SETTINGS_TIMEOUT_MS = 8_000;

/** Global safety timeout (ms) for the entire initialization. */
const INIT_GLOBAL_TIMEOUT_MS = 15_000;

export async function initializeApplication({
  configService,
  themeService,
  authService,
  loggerService,
  userSettingsApi,
  titleService,
  isBrowser,
}: InitializeApplicationDeps): Promise<void> {
  // Initialize browser logging as early as possible
  loggerService.init();

  if (!isBrowser) {
    return;
  }

  // Wrap entire initialization in a global timeout to prevent indefinite hangs
  const initWork = async (): Promise<void> => {
    console.debug('[AppInit] Loading config…');
    await configService.loadConfig();
    console.debug('[AppInit] Config loaded');

    authService.initMockAuth();
    await firstValueFrom(authService.restoreSession());

    const defaultTheme = configService.settings.theme as ThemeName;
    themeService.initializeTheme(defaultTheme);

    // Inject Configurable Skeleton Debounce duration as CSS Variable
    try {
      const debounceMs = configService.settings.skeletonDebounceDurationMs ?? 500;
      document.documentElement.style.setProperty('--skeleton-debounce-duration', `${debounceMs}ms`);
    } catch {
      /* ignore on non-browser platforms */
    }

    if (authService.isAuthenticated()) {
      try {
        console.debug('[AppInit] Fetching user settings…');
        const settings = (await firstValueFrom(
          userSettingsApi.getMe().pipe(timeout(USER_SETTINGS_TIMEOUT_MS)),
        )) as ThemePreferencePayload;
        themeService.applyUserPreferences(settings, defaultTheme);
        console.debug('[AppInit] User settings applied');
      } catch {
        // Baseline theme is already applied synchronously above.
        console.debug('[AppInit] User settings fetch failed or timed out — using defaults');
      }
    }

    // Set browser tab title from config if available
    try {
      const cfgTitle = (configService.settings as AppTitleSettings).title;
      if (cfgTitle) {
        titleService.setTitle(String(cfgTitle));
      }
    } catch {
      /* ignore if Title is not available on this platform */
    }

    // Ensure SPA-only loads also reveal the correct brand once config is loaded
    try {
      document.documentElement.classList.add('app-brand-ready');
    } catch {
      /* ignore on non-browser platforms */
    }
  };

  try {
    await Promise.race([
      initWork(),
      new Promise<void>((_, reject) =>
        setTimeout(() => reject(new Error('App initialization timed out')), INIT_GLOBAL_TIMEOUT_MS),
      ),
    ]);
  } catch (err) {
    console.error('[AppInit] Initialization failed or timed out, continuing with defaults:', err);
    // Ensure brand-ready class is set so the UI shows even on failure
    try {
      document.documentElement.classList.add('app-brand-ready');
    } catch {
      /* ignore */
    }
  }

  console.debug('[AppInit] Initialization complete');
}

export const appConfig: ApplicationConfig = {
  providers: [
    provideZonelessChangeDetection(),
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([cacheInterceptor, authInterceptor])),
    provideApi(''),
    provideZard(),
    provideCharts(withDefaultRegisterables()),
    provideClientHydration(
      withEventReplay(),
      withHttpTransferCacheOptions({
        filter: (req) => !req.url.startsWith('/api/'),
      }),
    ),

    // Load runtime config then initialize theme and auth
    provideAppInitializer(() => {
      const configService = inject(ConfigService);
      const themeService = inject(ThemeService);
      const authService = inject(AuthService);
      const loggerService = inject(LoggerService);
      const platformId = inject(PLATFORM_ID);
      const userSettingsApi = inject(UserSettingsApiService);
      const titleService = inject(Title);

      return initializeApplication({
        configService,
        themeService,
        authService,
        loggerService,
        userSettingsApi,
        titleService,
        isBrowser: isPlatformBrowser(platformId),
      });
    }),

    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
