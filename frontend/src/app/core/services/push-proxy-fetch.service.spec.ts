import { TestBed } from '@angular/core/testing';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';
import { PushProxyFetchService } from './push-proxy-fetch.service';

describe('PushProxyFetchService', () => {
  let service: PushProxyFetchService;
  let authServiceMock: { getToken: ReturnType<typeof vi.fn> };
  let fetchStub: ReturnType<typeof vi.fn>;
  let originalFetch: typeof window.fetch;
  let localStorageMock: { getItem: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    authServiceMock = {
      getToken: vi.fn().mockReturnValue('live-jwt-token'),
    };

    localStorageMock = {
      getItem: vi.fn().mockReturnValue('stale-local-token'),
    };
    Object.defineProperty(globalThis, 'localStorage', {
      configurable: true,
      value: localStorageMock,
    });

    fetchStub = vi.fn(() => Promise.resolve(new Response('ok', { status: 200 })));
    originalFetch = window.fetch;
    window.fetch = fetchStub as unknown as typeof window.fetch;

    TestBed.configureTestingModule({
      providers: [
        PushProxyFetchService,
        { provide: AuthService, useValue: authServiceMock },
      ],
    });

    service = TestBed.inject(PushProxyFetchService);
  });

  afterEach(() => {
    window.fetch = originalFetch;
    TestBed.resetTestingModule();
    vi.restoreAllMocks();
  });

  it('proxies firebase installations calls with the live auth token instead of localStorage', async () => {
    await service.runWithGoogleApisProxy(async () => {
      const response = await window.fetch(
        'https://firebaseinstallations.googleapis.com/v1/projects/demo-project/installations/abc123/authTokens:generate',
        {
          method: 'POST',
          headers: {
            'X-Goog-Api-Key': 'firebase-web-api-key',
            'X-Goog-Firebase-Installations-Auth': 'fis-token-xyz',
          },
          body: JSON.stringify({ installation: { appId: 'app-123' } }),
        },
      );

      expect(response.status).toBe(200);
    });

    expect(fetchStub).toHaveBeenCalledTimes(1);
    const [url, init] = fetchStub.mock.calls[0];
    expect(url).toBe('/api/push-notifications/firebase-install-proxy/');

    const headers = new Headers((init as RequestInit).headers);
    expect(headers.get('Authorization')).toBe('Bearer live-jwt-token');
    expect(headers.get('X-Firebase-Path')).toBe('installations/abc123/authTokens:generate');
    expect(headers.get('X-Goog-Api-Key')).toBe('firebase-web-api-key');
    expect(headers.get('X-Firebase-Auth')).toBe('fis-token-xyz');
    expect((init as RequestInit).body).toBe(JSON.stringify({ installation: { appId: 'app-123' } }));
    expect(authServiceMock.getToken).toHaveBeenCalled();
    expect(localStorageMock.getItem).not.toHaveBeenCalled();
  });
});
