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
import { requestMetadataInterceptor } from '@/core/interceptors/request-metadata.interceptor';
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
import { firstValueFrom, timeout } from 'rxjs';
import { routes } from './app.routes';

import { RbacService } from '@/core/api/api/rbac.service';
import { RbacPermissions } from '@/core/api/model/rbac-permissions';
import { provideApi } from '@/core/api/provide-api';
import { RBAC_RULES } from '@/core/tokens/rbac.token';
import { isWindowsPlatform } from '@/shared/utils/ui-scale';
import { WritableSignal } from '@angular/core';
import { provideServiceWorker } from '@angular/service-worker';
import { ThemeName } from './core/theme.config';

type AppTitleSettings = {
  title?: string | null;
};

const DEFAULT_UI_SCALE_PERCENT = 100;
const MIN_UI_SCALE_PERCENT = 25;
const MAX_UI_SCALE_PERCENT = 125;
const DEFAULT_UI_AUTO_SCALE_ENABLED = false;
const DEFAULT_UI_AUTO_SCALE_REFERENCE_WIDTH = 1440;
const MIN_UI_AUTO_SCALE_REFERENCE_WIDTH = 1024;
const DEFAULT_UI_AUTO_SCALE_MIN_PERCENT = 95;
const DEFAULT_UI_AUTO_SCALE_MAX_PERCENT = 105;
const MIN_UI_AUTO_SCALE_PERCENT = 25;
const MAX_UI_AUTO_SCALE_PERCENT = 125;
const DEFAULT_UI_AUTO_SCALE_DESKTOP_ONLY = true;
const SIDEBAR_DESKTOP_LAYOUT_MIN_VIEWPORT_WIDTH = 1024;
const OVERLAY_MENU_DESKTOP_LAYOUT_MIN_VIEWPORT_WIDTH = 768;

let uiScaleResizeCleanup: (() => void) | null = null;
let uiScaleResizeRafId: number | null = null;

function applyGlobalUiScaleViewportDimensions(scaleFactor: number): void {
  const safeScaleFactor = Number.isFinite(scaleFactor) && scaleFactor > 0 ? scaleFactor : 1;

  document.documentElement.style.setProperty('--app-ui-scale', safeScaleFactor.toString());
  document.documentElement.style.setProperty(
    '--app-ui-scale-inverse',
    (1 / safeScaleFactor).toString(),
  );
  document.documentElement.style.setProperty(
    '--app-scaled-vw',
    `${window.innerWidth / safeScaleFactor}px`,
  );
  document.documentElement.style.setProperty(
    '--app-scaled-dvw',
    `${window.innerWidth / safeScaleFactor}px`,
  );
  document.documentElement.style.setProperty(
    '--app-scaled-vh',
    `${window.innerHeight / safeScaleFactor}px`,
  );
  document.documentElement.style.setProperty(
    '--app-scaled-dvh',
    `${window.innerHeight / safeScaleFactor}px`,
  );
}

function parseBooleanLike(value: boolean | string | null | undefined, fallback = false): boolean {
  if (typeof value === 'boolean') {
    return value;
  }

  if (typeof value === 'string') {
    const normalizedValue = value.trim().toLowerCase();
    if (['true', '1', 'yes', 'on'].includes(normalizedValue)) {
      return true;
    }
    if (['false', '0', 'no', 'off'].includes(normalizedValue)) {
      return false;
    }
  }

  return fallback;
}

function normalizeUiScalePercent(value: number | string | null | undefined): number {
  const numericValue =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number.parseFloat(value)
        : Number.NaN;

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_UI_SCALE_PERCENT;
  }

  return Math.min(MAX_UI_SCALE_PERCENT, Math.max(MIN_UI_SCALE_PERCENT, numericValue));
}

function normalizeUiAutoScaleReferenceWidth(value: number | string | null | undefined): number {
  const numericValue =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number.parseFloat(value)
        : Number.NaN;

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_UI_AUTO_SCALE_REFERENCE_WIDTH;
  }

  return Math.max(MIN_UI_AUTO_SCALE_REFERENCE_WIDTH, numericValue);
}

function normalizeUiAutoScaleMinPercent(value: number | string | null | undefined): number {
  const numericValue =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number.parseFloat(value)
        : Number.NaN;

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_UI_AUTO_SCALE_MIN_PERCENT;
  }

  return Math.min(100, Math.max(MIN_UI_AUTO_SCALE_PERCENT, numericValue));
}

function normalizeUiAutoScaleMaxPercent(value: number | string | null | undefined): number {
  const numericValue =
    typeof value === 'number'
      ? value
      : typeof value === 'string'
        ? Number.parseFloat(value)
        : Number.NaN;

  if (!Number.isFinite(numericValue)) {
    return DEFAULT_UI_AUTO_SCALE_MAX_PERCENT;
  }

  return Math.max(100, Math.min(MAX_UI_AUTO_SCALE_PERCENT, numericValue));
}

function isUiAutoScaleEnabled(
  settings: InitializeApplicationDeps['configService']['settings'],
): boolean {
  const uiAutoScaleEnabled = parseBooleanLike(
    settings.uiAutoScaleEnabled,
    DEFAULT_UI_AUTO_SCALE_ENABLED,
  );
  return uiAutoScaleEnabled;
}

function isOverlayDisplayModeActive(): boolean {
  if (typeof window === 'undefined' || typeof window.matchMedia !== 'function') {
    return false;
  }

  return (
    window.matchMedia('(display-mode: window-controls-overlay)').matches ||
    window.matchMedia('(display-mode: standalone)').matches
  );
}

function getDesktopAutoScaleMinViewportWidth(
  settings: InitializeApplicationDeps['configService']['settings'],
): number {
  const useOverlayMenu = parseBooleanLike(settings.useOverlayMenu, false);

  return useOverlayMenu || isOverlayDisplayModeActive()
    ? OVERLAY_MENU_DESKTOP_LAYOUT_MIN_VIEWPORT_WIDTH
    : SIDEBAR_DESKTOP_LAYOUT_MIN_VIEWPORT_WIDTH;
}

function computeEffectiveUiScalePercent(
  settings: InitializeApplicationDeps['configService']['settings'],
  viewportWidth: number,
): number {
  const baseScalePercent = normalizeUiScalePercent(settings.uiScalePercent);

  if (!isUiAutoScaleEnabled(settings)) {
    return baseScalePercent;
  }

  const uiAutoScaleDesktopOnly = parseBooleanLike(
    settings.uiAutoScaleDesktopOnly,
    DEFAULT_UI_AUTO_SCALE_DESKTOP_ONLY,
  );
  const desktopAutoScaleMinViewportWidth = getDesktopAutoScaleMinViewportWidth(settings);
  const referenceWidth = normalizeUiAutoScaleReferenceWidth(settings.uiAutoScaleReferenceWidth);
  const autoScaleMinPercent = normalizeUiAutoScaleMinPercent(settings.uiAutoScaleMinPercent);
  const autoScaleMaxPercent = Math.max(
    autoScaleMinPercent,
    normalizeUiAutoScaleMaxPercent(settings.uiAutoScaleMaxPercent),
  );
  const effectiveViewportWidth =
    uiAutoScaleDesktopOnly && viewportWidth < desktopAutoScaleMinViewportWidth
      ? desktopAutoScaleMinViewportWidth
      : viewportWidth;
  const autoFactorPercentRaw = (effectiveViewportWidth / referenceWidth) * 100;
  const autoFactorPercent = Math.min(
    autoScaleMaxPercent,
    Math.max(autoScaleMinPercent, autoFactorPercentRaw),
  );

  const autoScaledPercent = (baseScalePercent * autoFactorPercent) / 100;

  if (uiAutoScaleDesktopOnly && viewportWidth < desktopAutoScaleMinViewportWidth) {
    return Math.min(baseScalePercent, autoScaledPercent);
  }

  return autoScaledPercent;
}

function applyGlobalUiScale(value: number | string | null | undefined): void {
  const scalePercent = normalizeUiScalePercent(value);
  const scaleFactor = scalePercent / 100;
  applyGlobalUiScaleViewportDimensions(scaleFactor);

  if (scalePercent === DEFAULT_UI_SCALE_PERCENT) {
    document.documentElement.style.removeProperty('zoom');
    return;
  }

  document.documentElement.style.setProperty('zoom', scaleFactor.toString());
}

function applyGlobalUiScaleFromSettings(
  settings: InitializeApplicationDeps['configService']['settings'],
): void {
  applyGlobalUiScale(computeEffectiveUiScalePercent(settings, window.innerWidth));
}

function applyPlatformClasses(): void {
  if (typeof document === 'undefined') {
    return;
  }

  document.documentElement.classList.toggle('platform-windows', isWindowsPlatform());
}

function bindGlobalUiScaleResizeHandler(
  settings: InitializeApplicationDeps['configService']['settings'],
): void {
  uiScaleResizeCleanup?.();
  uiScaleResizeCleanup = null;

  applyGlobalUiScaleFromSettings(settings);

  const onResize = (): void => {
    if (uiScaleResizeRafId !== null) {
      cancelAnimationFrame(uiScaleResizeRafId);
    }

    uiScaleResizeRafId = window.requestAnimationFrame(() => {
      uiScaleResizeRafId = null;
      applyGlobalUiScaleFromSettings(settings);
    });
  };

  window.addEventListener('resize', onResize, { passive: true });
  uiScaleResizeCleanup = () => {
    window.removeEventListener('resize', onResize);
    if (uiScaleResizeRafId !== null) {
      cancelAnimationFrame(uiScaleResizeRafId);
      uiScaleResizeRafId = null;
    }
  };
}

export type InitializeApplicationDeps = {
  configService: ConfigService;
  themeService: ThemeService;
  authService: AuthService;
  loggerService: LoggerService;
  userSettingsApi: UserSettingsApiService;
  titleService: Title;
  isBrowser: boolean;
  rbacService: RbacService;
  rbacRulesSignal: WritableSignal<RbacPermissions>;
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
  rbacService,
  rbacRulesSignal,
}: InitializeApplicationDeps): Promise<void> {
  // Initialize browser logging as early as possible
  loggerService.init();

  if (!isBrowser) {
    return;
  }

  // Wrap entire initialization in a global timeout to prevent indefinite hangs
  const initWork = async (): Promise<void> => {
    applyPlatformClasses();

    console.debug('[AppInit] Loading config…');
    await configService.loadConfig();
    console.debug('[AppInit] Config loaded');

    bindGlobalUiScaleResizeHandler(configService.settings);

    authService.initMockAuth();
    const defaultTheme = configService.settings.theme as ThemeName;
    themeService.initializeTheme(defaultTheme);

    const restoreSession = authService.restoreSession?.bind(authService);
    if (typeof restoreSession === 'function') {
      try {
        await firstValueFrom(restoreSession());
      } catch (error) {
        console.debug(
          '[AppInit] Session restore failed or timed out — continuing with defaults',
          error,
        );
      }
    }

    // Inject Configurable Skeleton Debounce duration as CSS Variable
    try {
      const debounceMs = configService.settings.skeletonDebounceDurationMs ?? 500;
      document.documentElement.style.setProperty('--skeleton-debounce-duration', `${debounceMs}ms`);
    } catch {
      /* ignore on non-browser platforms */
    }

    if (authService.isAuthenticated()) {
      try {
        console.debug('[AppInit] Fetching user settings and RBAC rules…');
        const [settings, rbacRules] = await Promise.all([
          firstValueFrom(
            userSettingsApi.getMe().pipe(timeout(USER_SETTINGS_TIMEOUT_MS)),
          ) as Promise<ThemePreferencePayload>,
          firstValueFrom(
            rbacService.rbacMyPermissionsRetrieve().pipe(timeout(USER_SETTINGS_TIMEOUT_MS)),
          ),
        ]);
        themeService.applyUserPreferences(settings, defaultTheme);
        rbacRulesSignal.set(rbacRules);
        console.debug('[AppInit] User settings and RBAC rules applied');
      } catch (e) {
        // Baseline theme is already applied synchronously above.
        console.debug(
          '[AppInit] Fetching settings or RBAC failed or timed out — using defaults',
          e,
        );
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
    provideHttpClient(
      withFetch(),
      withInterceptors([requestMetadataInterceptor, cacheInterceptor, authInterceptor]),
    ),
    provideApi(''),
    provideZard(),
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
      const rbacService = inject(RbacService);
      const rbacRulesSignal = inject(RBAC_RULES);

      return initializeApplication({
        configService,
        themeService,
        authService,
        loggerService,
        userSettingsApi,
        titleService,
        rbacService,
        rbacRulesSignal,
        isBrowser: isPlatformBrowser(platformId),
      });
    }),

    provideServiceWorker('ngsw-worker.js', {
      enabled: !isDevMode(),
      registrationStrategy: 'registerWhenStable:30000',
    }),
  ],
};
