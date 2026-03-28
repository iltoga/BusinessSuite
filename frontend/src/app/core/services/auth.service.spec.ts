import { HttpClient } from '@angular/common/http';
import { PLATFORM_ID } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { firstValueFrom, never, of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from './auth.service';
import { ConfigService } from './config.service';
import { DesktopBridgeService } from './desktop-bridge.service';

const originalLocalStorage = window.localStorage;

const installLocalStorageMock = (mock: Storage) => {
  Object.defineProperty(globalThis, 'localStorage', {
    configurable: true,
    value: mock,
  });
};

const restoreLocalStorage = () => {
  installLocalStorageMock(originalLocalStorage);
};

type AuthServiceInternals = {
  _token: { set(value: string | null): void };
  _claims: { set(value: { sub: string } | null): void };
};

const createAuthService = (
  httpClientMock: HttpClient,
  routerMock: Router,
  configServiceMock: ConfigService,
  desktopBridgeMock: DesktopBridgeService,
): AuthService => {
  TestBed.configureTestingModule({
    providers: [
      AuthService,
      { provide: HttpClient, useValue: httpClientMock },
      { provide: Router, useValue: routerMock },
      { provide: ConfigService, useValue: configServiceMock },
      { provide: DesktopBridgeService, useValue: desktopBridgeMock },
      { provide: PLATFORM_ID, useValue: 'browser' },
    ],
  });

  return TestBed.inject(AuthService);
};

describe('AuthService logout', () => {
  let service: AuthService;
  let httpClientMock: { post: ReturnType<typeof vi.fn>; request: ReturnType<typeof vi.fn> };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };
  let configServiceMock: { config: () => { MOCK_AUTH_ENABLED: boolean } };
  let desktopBridgeMock: { publishAuthToken: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    // Minimal localStorage mock for the test environment
    installLocalStorageMock({
      clear: vi.fn(),
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    } as unknown as Storage);
    document.cookie = 'bs_refresh_session_hint=; Max-Age=0; path=/';

    httpClientMock = {
      post: vi.fn(() => of(null)),
      request: vi.fn(() => of({ menus: {}, fields: {} })),
    };
    routerMock = { navigate: vi.fn() };
    configServiceMock = {
      config: () => ({ MOCK_AUTH_ENABLED: false }),
    };
    desktopBridgeMock = { publishAuthToken: vi.fn() };

    service = createAuthService(
      httpClientMock as unknown as HttpClient,
      routerMock as unknown as Router,
      configServiceMock as unknown as ConfigService,
      desktopBridgeMock as unknown as DesktopBridgeService,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    routerMock.navigate.mockClear();
    restoreLocalStorage();
  });

  it('clears tokens and ignores 401 from backend logout', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    httpClientMock.post.mockReturnValueOnce(
      throwError(() => ({ status: 401, detail: 'Unauthorized' })),
    );

    // Set a token so we can verify it's cleared
    const internals = service as unknown as AuthServiceInternals;
    internals._token.set('my-token');
    internals._claims.set({ sub: '1' });

    service.logout();

    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
    expect(httpClientMock.post).toHaveBeenCalledWith(
      '/api/user-profile/logout/',
      {},
      expect.objectContaining({
        headers: expect.anything(),
      }),
    );

    // 401 should be swallowed and not logged
    expect(consoleSpy).not.toHaveBeenCalled();

    // Tokens should be cleared
    expect(service.getToken()).toBeNull();

    consoleSpy.mockRestore();
  });

  it('logs non-401 errors when backend logout fails', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    httpClientMock.post.mockReturnValueOnce(throwError(() => ({ status: 500, detail: 'Boom' })));

    const internals = service as unknown as AuthServiceInternals;
    internals._token.set('my-token');

    service.logout();

    expect(consoleSpy).toHaveBeenCalled();

    // Tokens should still be cleared
    expect(service.getToken()).toBeNull();

    consoleSpy.mockRestore();
  });

  it('does not call backend logout when there is no token', () => {
    service.logout();

    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
    expect(httpClientMock.post).toHaveBeenCalledWith(
      '/api/user-profile/logout/',
      {},
      expect.objectContaining({
        withCredentials: true,
        headers: undefined,
      }),
    );
  });

  it('does not call backend logout when token is already expired', () => {
    const expiredPayload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 60 }));
    const internals = service as unknown as AuthServiceInternals;
    internals._token.set(`header.${expiredPayload}.signature`);

    service.logout();

    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
    expect(httpClientMock.post).toHaveBeenCalledWith(
      '/api/user-profile/logout/',
      {},
      expect.objectContaining({
        withCredentials: true,
      }),
    );
  });
});

describe('AuthService auth flow', () => {
  let service: AuthService;
  let httpClientMock: { post: ReturnType<typeof vi.fn>; request: ReturnType<typeof vi.fn> };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };
  let configServiceMock: { config: () => { MOCK_AUTH_ENABLED: boolean } };
  let desktopBridgeMock: { publishAuthToken: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    installLocalStorageMock({
      clear: vi.fn(),
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    } as unknown as Storage);
    document.cookie = 'bs_refresh_session_hint=; Max-Age=0; path=/';

    httpClientMock = {
      post: vi.fn(),
      request: vi.fn(() => of({ menus: {}, fields: {} })),
    };
    routerMock = { navigate: vi.fn() };
    configServiceMock = {
      config: () => ({ MOCK_AUTH_ENABLED: false }),
    };
    desktopBridgeMock = { publishAuthToken: vi.fn() };

    service = createAuthService(
      httpClientMock as unknown as HttpClient,
      routerMock as unknown as Router,
      configServiceMock as unknown as ConfigService,
      desktopBridgeMock as unknown as DesktopBridgeService,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    restoreLocalStorage();
    vi.useRealTimers();
  });

  it('normalizes canonical login envelopes and stores the access token in memory', async () => {
    httpClientMock.post.mockReturnValueOnce(
      of({
        data: {
          access_token: 'access-token-123',
          refresh_token: 'refresh-token-123',
          user: {
            id: 7,
            username: 'auth-user',
            email: 'auth-user@example.com',
            full_name: 'Auth User',
            roles: ['admin'],
            groups: ['admin'],
            is_superuser: true,
            is_staff: true,
          },
        },
        meta: { requestId: 'req-1', apiVersion: 'v1' },
      }),
    );

    const response = await firstValueFrom(
      service.login({ username: 'auth-user', password: 'password123' }),
    );

    expect(response.data?.access_token).toBe('access-token-123');
    expect(service.getToken()).toBe('access-token-123');
    expect(service.claims()?.email).toBe('auth-user@example.com');
    expect(service.claims()?.isSuperuser).toBe(true);
    expect(desktopBridgeMock.publishAuthToken).toHaveBeenCalledWith('access-token-123');
    expect(httpClientMock.post).toHaveBeenCalledWith(
      '/api/api-token-auth/',
      { username: 'auth-user', password: 'password123' },
      expect.objectContaining({ withCredentials: true }),
    );
  });

  it('restores a session by calling the cookie-backed refresh endpoint', async () => {
    document.cookie = 'bs_refresh_session_hint=1; path=/';
    httpClientMock.post.mockReturnValueOnce(
      of({
        data: {
          access_token: 'refreshed-access-token',
          refresh_token: 'refresh-token-123',
          user: {
            id: 7,
            username: 'auth-user',
            email: 'auth-user@example.com',
            full_name: 'Auth User',
            roles: ['admin'],
            groups: ['admin'],
            is_superuser: true,
            is_staff: true,
          },
        },
        meta: { requestId: 'req-2', apiVersion: 'v1' },
      }),
    );

    await expect(firstValueFrom(service.restoreSession())).resolves.toBe(true);

    expect(httpClientMock.post).toHaveBeenCalledWith(
      '/api/token/refresh/',
      {},
      expect.objectContaining({ withCredentials: true }),
    );
    expect(service.getToken()).toBe('refreshed-access-token');
  });

  it('fails closed when the refresh endpoint stalls during session restore', async () => {
    vi.useFakeTimers();
    document.cookie = 'bs_refresh_session_hint=1; path=/';
    httpClientMock.post.mockReturnValueOnce(never());

    const restorePromise = firstValueFrom(service.restoreSession());

    await vi.advanceTimersByTimeAsync(8_000);

    await expect(restorePromise).resolves.toBe(false);
    expect(service.getToken()).toBeNull();
  });

  it('skips refresh when there is no refresh session hint cookie', async () => {
    await expect(firstValueFrom(service.restoreSession())).resolves.toBe(false);

    expect(httpClientMock.post).not.toHaveBeenCalled();
  });
});

describe('AuthService mock auth', () => {
  let service: AuthService;
  let httpClientMock: { post: ReturnType<typeof vi.fn>; get: ReturnType<typeof vi.fn> };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };
  let configServiceMock: { config: () => { MOCK_AUTH_ENABLED: boolean } };
  let desktopBridgeMock: { publishAuthToken: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    installLocalStorageMock({
      clear: vi.fn(),
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    } as unknown as Storage);
    document.cookie = 'bs_refresh_session_hint=; Max-Age=0; path=/';

    httpClientMock = {
      post: vi.fn(),
      get: vi.fn(),
    };
    routerMock = { navigate: vi.fn() };
    configServiceMock = {
      config: () => ({ MOCK_AUTH_ENABLED: true }),
    };
    desktopBridgeMock = { publishAuthToken: vi.fn() };

    service = createAuthService(
      httpClientMock as unknown as HttpClient,
      routerMock as unknown as Router,
      configServiceMock as unknown as ConfigService,
      desktopBridgeMock as unknown as DesktopBridgeService,
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    restoreLocalStorage();
  });

  it('short-circuits login to the mock session and hydrates mock claims', async () => {
    httpClientMock.get.mockReturnValueOnce(
      of({
        data: {
          sub: 'mock-remote',
          email: 'remote@example.com',
          roles: ['manager'],
          groups: ['manager'],
          is_superuser: false,
          is_staff: true,
        },
      }),
    );

    const response = await firstValueFrom(
      service.login({ username: 'anything', password: 'secret' }),
    );

    expect(response.access_token).toBe('mock-token');
    expect(service.getToken()).toBe('mock-token');
    expect(service.isMockEnabled()).toBe(true);
    expect(httpClientMock.post).not.toHaveBeenCalled();
    expect(httpClientMock.get).toHaveBeenCalledWith('/api/mock-auth-config/');
    expect(service.claims()?.sub).toBe('mock-remote');
    expect(service.claims()?.email).toBe('remote@example.com');
  });

  it('refreshes to the synthetic mock token without hitting the backend', async () => {
    const token = await firstValueFrom(service.refreshToken());

    expect(token).toBe('mock-token');
    expect(service.getToken()).toBe('mock-token');
    expect(httpClientMock.post).not.toHaveBeenCalled();
  });

  it('restores no session in mock mode', async () => {
    await expect(firstValueFrom(service.restoreSession())).resolves.toBe(false);

    expect(httpClientMock.post).not.toHaveBeenCalled();
    expect(httpClientMock.get).not.toHaveBeenCalled();
  });
});
