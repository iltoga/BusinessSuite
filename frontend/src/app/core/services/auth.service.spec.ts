import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { vi } from 'vitest';

import { AuthService } from './auth.service';

describe('AuthService logout', () => {
  let service: AuthService;
  let httpMock: HttpTestingController;
  const routerMock: any = { navigate: vi.fn() };

  beforeEach(() => {
    // Minimal localStorage mock for the test environment
    (globalThis as any).localStorage = {
      getItem: vi.fn().mockReturnValue(null),
      setItem: vi.fn(),
      removeItem: vi.fn(),
    };

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [{ provide: Router, useValue: routerMock }],
    });

    service = TestBed.inject(AuthService);
    httpMock = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpMock.verify();
    vi.restoreAllMocks();
    routerMock.navigate.mockClear();
  });

  it('clears tokens and ignores 401 from backend logout', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    // Set a token so we can verify it's cleared
    (service as any)._token.set('my-token');
    (service as any)._claims.set({ sub: '1' });

    service.logout();

    expect(routerMock.navigate).toHaveBeenCalledWith(['/login']);

    const req = httpMock.expectOne('/api/user-profile/logout/');
    expect(req.request.method).toBe('POST');

    req.flush({ detail: 'Unauthorized' }, { status: 401, statusText: 'Unauthorized' });

    // 401 should be swallowed and not logged
    expect(consoleSpy).not.toHaveBeenCalled();

    // Tokens should be cleared
    expect(service.getToken()).toBeNull();

    consoleSpy.mockRestore();
  });

  it('logs non-401 errors when backend logout fails', () => {
    const consoleSpy = vi.spyOn(console, 'error').mockImplementation(() => {});

    (service as any)._token.set('my-token');

    service.logout();

    const req = httpMock.expectOne('/api/user-profile/logout/');
    expect(req.request.method).toBe('POST');

    req.flush({ detail: 'Boom' }, { status: 500, statusText: 'Server Error' });

    expect(consoleSpy).toHaveBeenCalled();

    // Tokens should still be cleared
    expect(service.getToken()).toBeNull();

    consoleSpy.mockRestore();
  });
});
