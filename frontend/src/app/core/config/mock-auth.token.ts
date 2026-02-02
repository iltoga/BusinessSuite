import { InjectionToken } from '@angular/core';

/**
 * Set this provider to `true` in `appConfig.providers` to enable mocked authentication for local dev
 */
export const MOCK_AUTH_ENABLED = new InjectionToken<boolean>('MOCK_AUTH_ENABLED');
