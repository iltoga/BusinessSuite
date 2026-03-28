import { inject } from '@angular/core';
import { Router, type CanActivateFn } from '@angular/router';

import { RBAC_RULES } from '@/core/tokens/rbac.token';
import { AuthService } from '@/core/services/auth.service';

export const rbacMenuGuard: CanActivateFn = (route) => {
  const rbacRulesSignal = inject(RBAC_RULES);
  const authService = inject(AuthService);
  const router = inject(Router);

  const menuId = route.data?.['menuId'] as string | undefined;
  if (!menuId) {
    return true;
  }

  const rules = rbacRulesSignal();
  const isVisible = rules.menus?.[menuId];

  // If there's an explicit false rule, block.
  if (isVisible === false) {
    return router.createUrlTree(['/dashboard']);
  }

  // If there is no rule, fallback to allowing if no fallback strategy is defined
  // For 'reports', we maintain backward compatibility
  if (isVisible === undefined && menuId === 'reports') {
    if (!authService.isAdminOrManager()) {
      return router.createUrlTree(['/dashboard']);
    }
  }

  return true;
};
