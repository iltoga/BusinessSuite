import { provideHttpClient, withFetch, withInterceptors } from '@angular/common/http';
import { ApplicationConfig, provideBrowserGlobalErrorListeners } from '@angular/core';
import { provideRouter } from '@angular/router';

import { authInterceptor } from '@/core/interceptors/auth.interceptor';
import { provideZard } from '@/shared/core/provider/providezard';
import { provideClientHydration, withEventReplay } from '@angular/platform-browser';
import { routes } from './app.routes';

import { APP_CONFIG } from './core/config/app.config';
import { MOCK_AUTH_ENABLED } from './core/config/mock-auth.token';

export const appConfig: ApplicationConfig = {
  providers: [
    provideBrowserGlobalErrorListeners(),
    provideRouter(routes),
    provideHttpClient(withFetch(), withInterceptors([authInterceptor])),
    provideZard(),
    provideClientHydration(withEventReplay()),

    // Mocked authentication (toggle in src/app/core/config/app.config.ts)
    {
      provide: MOCK_AUTH_ENABLED,
      useValue: APP_CONFIG.mockAuthEnabled,
    },
  ],
};
