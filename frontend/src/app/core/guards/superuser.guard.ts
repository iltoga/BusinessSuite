import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../services/auth.service';

export const superuserGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);

  if (authService.isAuthenticated() && authService.isSuperuser()) {
    return true;
  }

  if (!authService.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  // User is authenticated but not a superuser - show access denied
  return router.createUrlTree(['/dashboard'], {
    queryParams: { error: 'Access denied. Admin privileges required.' },
  });
};
