import { InjectionToken, signal, WritableSignal } from '@angular/core';
import { RbacPermissions } from '@/core/api/model/rbac-permissions';

/**
 * Injection Token providing a globally available, reactive signal
 * containing the current user's dynamic RBAC rules.
 * Natively fetched via OpenAPI generated client in app.config.ts / AuthService.
 */
export const RBAC_RULES = new InjectionToken<WritableSignal<RbacPermissions>>('RBAC_RULES', {
  providedIn: 'root',
  factory: () => signal<RbacPermissions>({ menus: {}, fields: {} })
});
