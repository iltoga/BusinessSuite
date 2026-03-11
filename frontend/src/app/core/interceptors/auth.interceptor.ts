import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { throwError } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { AuthService } from '@/core/services/auth.service';

const isTokenEndpoint = (url?: string | null): boolean =>
  Boolean(url?.endsWith('/api/api-token-auth/') || url?.endsWith('/token/refresh/'));

const isLogoutEndpoint = (url?: string | null): boolean =>
  Boolean(url?.includes('/user-profile/logout'));

const withAuthorizationHeader = (req: Parameters<HttpInterceptorFn>[0], token: string) =>
  req.clone({
    setHeaders: {
      Authorization: `Bearer ${token}`,
    },
  });

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const token = authService.getToken();

  const sendRequest = (request = req) =>
    next(request).pipe(
      catchError((err: any) => {
        if (err?.status !== 401) {
          return throwError(() => err);
        }

        if (isTokenEndpoint(request.url)) {
          authService.logout();
          return throwError(() => err);
        }

        if (isLogoutEndpoint(request.url)) {
          return throwError(() => err);
        }

        return authService.refreshToken().pipe(
          switchMap(() => {
            const refreshedToken = authService.getToken();
            if (!refreshedToken) {
              authService.logout();
              return throwError(() => err);
            }
            return next(withAuthorizationHeader(req, refreshedToken));
          }),
          catchError((refreshErr) => {
            authService.logout();
            return throwError(() => refreshErr);
          }),
        );
      }),
    );

  if (
    token &&
    authService.isTokenExpired(token) &&
    !isTokenEndpoint(req.url) &&
    !isLogoutEndpoint(req.url)
  ) {
    return authService.refreshToken().pipe(
      switchMap(() => {
        const refreshedToken = authService.getToken();
        if (!refreshedToken || authService.isTokenExpired(refreshedToken)) {
          authService.logout();
          return throwError(() => new Error('Token expired'));
        }
        return sendRequest(withAuthorizationHeader(req, refreshedToken));
      }),
      catchError((refreshErr) => {
        authService.logout();
        return throwError(() => refreshErr);
      }),
    );
  }

  return sendRequest(token ? withAuthorizationHeader(req, token) : req);
};
