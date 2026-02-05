import { HTTP_INTERCEPTORS, HttpClient } from '@angular/common/http';
import { HttpClientTestingModule, HttpTestingController } from '@angular/common/http/testing';
import { TestBed } from '@angular/core/testing';
import { of, throwError } from 'rxjs';
import { tap } from 'rxjs/operators';
import { vi } from 'vitest';

import { AuthService } from '@/core/services/auth.service';
import { authInterceptor } from './auth.interceptor';

// Helper to adapt function-style interceptor to class provider for HTTP_INTERCEPTORS
import type { HttpHandler, HttpInterceptor, HttpRequest } from '@angular/common/http';
class WrapperInterceptor implements HttpInterceptor {
  intercept(req: HttpRequest<any>, next: HttpHandler) {
    // adapt HttpHandler to the functional "next" expected by the HttpInterceptorFn
    const nextFn = (r: any) => next.handle(r);
    return authInterceptor(req as any, nextFn as any) as any;
  }
}

describe('authInterceptor', () => {
  let http: HttpClient;
  let httpTestingController: HttpTestingController;
  let mockAuth: any;

  beforeEach(() => {
    mockAuth = {
      getToken: vi.fn().mockReturnValue(null),
      isTokenExpired: vi.fn().mockReturnValue(false),
      logout: vi.fn(),
    };

    TestBed.configureTestingModule({
      imports: [HttpClientTestingModule],
      providers: [
        { provide: AuthService, useValue: mockAuth },
        { provide: HTTP_INTERCEPTORS, useClass: WrapperInterceptor, multi: true },
      ],
    });

    http = TestBed.inject(HttpClient);
    httpTestingController = TestBed.inject(HttpTestingController);
  });

  afterEach(() => {
    httpTestingController.verify();
  });

  it('adds Authorization header when token present and not expired', () => {
    mockAuth.getToken.mockReturnValue('my-token');
    mockAuth.isTokenExpired.mockReturnValue(false);

    return new Promise<void>((resolve) => {
      http.get('/some-url').subscribe(() => resolve());

      const req = httpTestingController.expectOne('/some-url');
      expect(req.request.headers.get('Authorization')).toBe('Bearer my-token');
      req.flush({ ok: true });
    });
  });

  it('calls logout and fails the request immediately when token is expired', () => {
    mockAuth.getToken.mockReturnValue('expired');
    mockAuth.isTokenExpired.mockReturnValue(true);

    return new Promise<void>((resolve) => {
      http.get('/no-request').subscribe({
        next: () => {
          throw new Error('should not succeed');
        },
        error: () => {
          expect(mockAuth.logout).toHaveBeenCalled();
          // ensure no network request was performed
          httpTestingController.expectNone('/no-request');
          resolve();
        },
      });
    });
  });

  it('logs out when server returns 401', () => {
    mockAuth.getToken.mockReturnValue('valid-token');
    mockAuth.isTokenExpired.mockReturnValue(false);

    mockAuth.refreshToken = vi.fn().mockReturnValue(throwError(() => new Error('no refresh')));

    return new Promise<void>((resolve) => {
      http.get('/forbidden').subscribe({
        next: () => {
          throw new Error('should not succeed');
        },
        error: () => {
          expect(mockAuth.logout).toHaveBeenCalled();
          resolve();
        },
      });

      const req = httpTestingController.expectOne('/forbidden');
      req.flush(null, { status: 401, statusText: 'Unauthorized' });
    });
  });

  it('attempts refresh and retries the original request on 401', () => {
    mockAuth.getToken.mockReturnValue('old-token');
    mockAuth.isTokenExpired.mockReturnValue(false);

    // When refreshToken is called, update getToken to return new token
    mockAuth.refreshToken = vi.fn().mockReturnValue(
      of('new-token').pipe(
        tap(() => {
          mockAuth.getToken.mockReturnValue('new-token');
        }),
      ),
    );

    return new Promise<void>((resolve) => {
      http.get('/protected').subscribe({
        next: () => {
          resolve();
        },
        error: () => {
          throw new Error('should not error');
        },
      });

      const req1 = httpTestingController.expectOne('/protected');
      // first attempt fails with 401
      req1.flush(null, { status: 401, statusText: 'Unauthorized' });

      // after refresh, the interceptor should retry the request
      const req2 = httpTestingController.expectOne('/protected');
      expect(req2.request.headers.get('Authorization')).toBe('Bearer new-token');
      req2.flush({ ok: true });
    });
  });
});
