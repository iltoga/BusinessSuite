import { HttpClient } from '@angular/common/http';
import { Router } from '@angular/router';
import { of, throwError } from 'rxjs';
import { vi } from 'vitest';

import { AuthService } from './auth.service';
import { ConfigService } from './config.service';
import { DesktopBridgeService } from './desktop-bridge.service';

describe('AuthService logout', () => {
  let service: AuthService;
  let httpClientMock: { post: ReturnType<typeof vi.fn> };
  let routerMock: { navigate: ReturnType<typeof vi.fn> };
  let configServiceMock: { config: () => { MOCK_AUTH_ENABLED: boolean } };
  let desktopBridgeMock: { publishAuthToken: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    // Minimal localStorage mock for the test environment
    (globalThis as any).localStorage = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };

    httpClientMock = {
      post: vi.fn(() => of(null)),
    };
    routerMock = { navigate: vi.fn() };
    configServiceMock = {
      config: () => ({ MOCK_AUTH_ENABLED: false }),
    };
    desktopBridgeMock = { publishAuthToken: vi.fn() };

    service = new AuthService(
      httpClientMock as unknown as HttpClient,
      routerMock as unknown as Router,
      configServiceMock as unknown as ConfigService,
      desktopBridgeMock as unknown as DesktopBridgeService,
      'browser',
    );
  });

  afterEach(() => {
    vi.restoreAllMocks();
    routerMock.navigate.mockClear();
  });

  it('clears tokens and ignores 401 from backend logout', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});
    httpClientMock.post.mockReturnValueOnce(
      throwError(() => ({ status: 401, detail: 'Unauthorized' })),
    );

    // Set a token so we can verify it's cleared
    (service as any)._token.set('my-token');
    (service as any)._claims.set({ sub: '1' });

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

    (service as any)._token.set('my-token');

    service.logout();

    expect(consoleSpy).toHaveBeenCalled();

    // Tokens should still be cleared
    expect(service.getToken()).toBeNull();

    consoleSpy.mockRestore();
  });

  it('does not call backend logout when there is no token', () => {
    service.logout();

    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
    expect(httpClientMock.post).not.toHaveBeenCalled();
  });

  it('does not call backend logout when token is already expired', () => {
    const expiredPayload = btoa(JSON.stringify({ exp: Math.floor(Date.now() / 1000) - 60 }));
    (service as any)._token.set(`header.${expiredPayload}.signature`);

    service.logout();

    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);
    expect(httpClientMock.post).not.toHaveBeenCalled();
  });
});
