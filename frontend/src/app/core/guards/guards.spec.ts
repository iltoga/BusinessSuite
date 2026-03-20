import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import {
  ActivatedRouteSnapshot,
  type CanActivateFn,
  Router,
  RouterStateSnapshot,
} from '@angular/router';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';
import { adminGroupGuard } from './admin-group.guard';
import { adminOrManagerGuard } from './admin-or-manager.guard';
import { authGuard } from './auth.guard';
import { staffGuard } from './staff.guard';
import { superuserGuard } from './superuser.guard';

type AuthMock = {
  isAuthenticated: ReturnType<typeof vi.fn>;
  isMockEnabled: ReturnType<typeof vi.fn>;
  getToken: ReturnType<typeof vi.fn>;
  isInAdminGroup: ReturnType<typeof vi.fn>;
  isInManagerGroup: ReturnType<typeof vi.fn>;
  isAdminOrManager: ReturnType<typeof vi.fn>;
  isSuperuser: ReturnType<typeof vi.fn>;
  isStaff: ReturnType<typeof vi.fn>;
};

const createAuthMock = (overrides: Partial<AuthMock> = {}): AuthMock =>
  ({
    isAuthenticated: vi.fn(() => true),
    isMockEnabled: vi.fn(() => false),
    getToken: vi.fn(() => 'token'),
    isInAdminGroup: vi.fn(() => false),
    isInManagerGroup: vi.fn(() => false),
    isAdminOrManager: vi.fn(() => false),
    isSuperuser: vi.fn(() => false),
    isStaff: vi.fn(() => false),
    ...overrides,
  }) as AuthMock;

const createRouterMock = () => ({
  createUrlTree: vi.fn((commands: unknown[], extras?: unknown) => ({ commands, extras })),
});

describe('route guards', () => {
  beforeEach(() => {
    TestBed.resetTestingModule();
  });

  afterEach(() => {
    vi.restoreAllMocks();
  });

  const runGuard = (
    guard: CanActivateFn,
    options: { platformId?: 'browser' | 'server'; auth?: Partial<AuthMock> } = {},
  ) => {
    const router = createRouterMock();
    const auth = createAuthMock(options.auth);

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: options.platformId ?? 'browser' },
        { provide: Router, useValue: router },
        { provide: AuthService, useValue: auth },
      ],
    });

    const route = {} as ActivatedRouteSnapshot;
    const state = { url: '/test' } as RouterStateSnapshot;
    const result = TestBed.runInInjectionContext(() => guard(route, state));
    return { result, router, auth };
  };

  it('authGuard allows authenticated browser users', () => {
    const { result, router } = runGuard(authGuard);

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('authGuard redirects anonymous users to login', () => {
    const { result, router } = runGuard(authGuard, {
      auth: {
        isAuthenticated: vi.fn(() => false),
      },
    });

    expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
    expect(result).toEqual({ commands: ['/login'], extras: undefined });
  });

  it('authGuard allows mock-token access when mock auth is enabled', () => {
    const { result, router } = runGuard(authGuard, {
      auth: {
        isAuthenticated: vi.fn(() => false),
        isMockEnabled: vi.fn(() => true),
        getToken: vi.fn(() => 'mock-token'),
      },
    });

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('authGuard bypasses auth checks on the server', () => {
    const { result, router } = runGuard(authGuard, {
      platformId: 'server',
      auth: {
        isAuthenticated: vi.fn(() => false),
      },
    });

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('adminGroupGuard allows authenticated admins', () => {
    const { result, router } = runGuard(adminGroupGuard, {
      auth: {
        isInAdminGroup: vi.fn(() => true),
      },
    });

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('adminGroupGuard sends anonymous users to login', () => {
    const { result, router } = runGuard(adminGroupGuard, {
      auth: {
        isAuthenticated: vi.fn(() => false),
      },
    });

    expect(result).toEqual({ commands: ['/login'], extras: undefined });
    expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
  });

  it('adminGroupGuard returns dashboard access denied for non-admin members', () => {
    const { result, router } = runGuard(adminGroupGuard, {
      auth: {
        isAuthenticated: vi.fn(() => true),
      },
    });

    expect(router.createUrlTree).toHaveBeenCalledWith(['/dashboard'], {
      queryParams: { error: "Access denied. 'admin' group membership required." },
    });
    expect(result).toEqual({
      commands: ['/dashboard'],
      extras: {
        queryParams: { error: "Access denied. 'admin' group membership required." },
      },
    });
  });

  it('staffGuard allows staff and admin-group members', () => {
    const { result, router } = runGuard(staffGuard, {
      auth: {
        isStaff: vi.fn(() => true),
      },
    });

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('staffGuard returns dashboard access denied for authenticated non-staff users', () => {
    const { result, router } = runGuard(staffGuard, {
      auth: {
        isAuthenticated: vi.fn(() => true),
      },
    });

    expect(router.createUrlTree).toHaveBeenCalledWith(['/dashboard'], {
      queryParams: { error: 'Access denied. Staff or admin-group privileges required.' },
    });
    expect(result).toEqual({
      commands: ['/dashboard'],
      extras: {
        queryParams: { error: 'Access denied. Staff or admin-group privileges required.' },
      },
    });
  });

  it('adminOrManagerGuard allows authenticated admins or managers', () => {
    const { result, router } = runGuard(adminOrManagerGuard, {
      auth: {
        isAdminOrManager: vi.fn(() => true),
      },
    });

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('adminOrManagerGuard sends anonymous users to login', () => {
    const { result, router } = runGuard(adminOrManagerGuard, {
      auth: {
        isAuthenticated: vi.fn(() => false),
      },
    });

    expect(result).toEqual({ commands: ['/login'], extras: undefined });
    expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
  });

  it('adminOrManagerGuard returns dashboard access denied for authenticated non-managers', () => {
    const { result, router } = runGuard(adminOrManagerGuard, {
      auth: {
        isAuthenticated: vi.fn(() => true),
      },
    });

    expect(router.createUrlTree).toHaveBeenCalledWith(['/dashboard'], {
      queryParams: { error: 'Access denied. Admin or manager privileges required.' },
    });
    expect(result).toEqual({
      commands: ['/dashboard'],
      extras: {
        queryParams: { error: 'Access denied. Admin or manager privileges required.' },
      },
    });
  });

  it('superuserGuard allows superusers and admin-group members', () => {
    const { result, router } = runGuard(superuserGuard, {
      auth: {
        isSuperuser: vi.fn(() => true),
      },
    });

    expect(result).toBe(true);
    expect(router.createUrlTree).not.toHaveBeenCalled();
  });

  it('superuserGuard sends anonymous users to login', () => {
    const { result, router } = runGuard(superuserGuard, {
      auth: {
        isAuthenticated: vi.fn(() => false),
      },
    });

    expect(result).toEqual({ commands: ['/login'], extras: undefined });
    expect(router.createUrlTree).toHaveBeenCalledWith(['/login']);
  });

  it('superuserGuard returns dashboard access denied for authenticated non-superusers', () => {
    const { result, router } = runGuard(superuserGuard, {
      auth: {
        isAuthenticated: vi.fn(() => true),
      },
    });

    expect(router.createUrlTree).toHaveBeenCalledWith(['/dashboard'], {
      queryParams: {
        error: 'Access denied. Superuser or admin-group privileges required.',
      },
    });
    expect(result).toEqual({
      commands: ['/dashboard'],
      extras: {
        queryParams: {
          error: 'Access denied. Superuser or admin-group privileges required.',
        },
      },
    });
  });
});
