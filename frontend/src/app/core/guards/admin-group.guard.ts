import { inject } from '@angular/core';
import { CanActivateFn, Router } from '@angular/router';

import { AuthService } from '../services/auth.service';
import { ConfigService } from '../services/config.service';

export const adminGroupGuard: CanActivateFn = () => {
  const authService = inject(AuthService);
  const router = inject(Router);
  const configService = inject(ConfigService);

  if (authService.isAuthenticated() && authService.isInAdminGroup()) {
    return true;
  }

  if (!authService.isAuthenticated()) {
    return router.createUrlTree(['/login']);
  }

  const groupName = configService.config().rbac?.adminGroupName ?? 'admin';
  return router.createUrlTree(['/dashboard'], {
    queryParams: { error: `Access denied. '${groupName}' group membership required.` },
  });
};
