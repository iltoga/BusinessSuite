import { HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { throwError } from 'rxjs';
import { catchError, switchMap } from 'rxjs/operators';

import { AuthService } from '@/core/services/auth.service';

export const authInterceptor: HttpInterceptorFn = (req, next) => {
  const authService = inject(AuthService);
  const token = authService.getToken();

  // If token is present but expired, force logout immediately and stop the request
  if (token && authService.isTokenExpired(token)) {
    authService.logout();
    return throwError(() => new Error('Token expired'));
  }

  if (token) {
    req = req.clone({
      setHeaders: {
        Authorization: `Bearer ${token}`,
      },
    });
  }

  return next(req).pipe(
    // If any response returns 401, attempt refresh and retry once
    catchError((err: any) => {
      if (err?.status === 401) {
        // Avoid loops for token obtain and refresh endpoints
        if (req.url?.endsWith('/api/api-token-auth/') || req.url?.endsWith('/token/refresh/')) {
          authService.logout();
          return throwError(() => err);
        }

        // If backend returned 401 for the logout endpoint, do not try to refresh or call logout again
        if (req.url?.includes('/user-profile/logout')) {
          return throwError(() => err);
        }

        // Try to refresh token and retry original request
        return authService.refreshToken().pipe(
          switchMap(() => {
            const newToken = authService.getToken();
            if (!newToken) {
              authService.logout();
              return throwError(() => err);
            }
            const retryReq = req.clone({
              setHeaders: { Authorization: `Bearer ${newToken}` },
            });
            return next(retryReq);
          }),
          catchError((refreshErr) => {
            authService.logout();
            return throwError(() => refreshErr);
          }),
        );
      }
      return throwError(() => err);
    }),
  );
};
