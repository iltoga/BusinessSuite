import { isPlatformServer } from '@angular/common';
import { inject, PLATFORM_ID } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';
import { firstValueFrom } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export const authGuard: CanActivateFn = async () => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const platformId = inject(PLATFORM_ID);

  // Skip auth check on server-side rendering - let browser handle it after hydration
  if (isPlatformServer(platformId)) {
    return true;
  }

  if (authService.isAuthenticated()) {
    return true;
  }

  // Final check for mock mode - in case signals are still settling
  if (authService.isMockEnabled() && authService.getToken() === 'mock-token') {
    return true;
  }

  const restoreSession = authService.restoreSession?.bind(authService);
  if (typeof restoreSession === 'function') {
    try {
      const restored = await firstValueFrom(restoreSession());
      if (restored || authService.isAuthenticated()) {
        return true;
      }
    } catch {
      // Fall through to the login redirect when session restoration fails.
    }
  }

  return router.createUrlTree(['/login']);
};
