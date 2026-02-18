import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { HttpHeaders } from '@angular/common/http';
import { computed, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, finalize, map, Observable, of, shareReplay, tap, throwError } from 'rxjs';

import { ConfigService } from './config.service';

export interface AuthToken {
  token?: string;
  access?: string;
  refresh?: string;
}

export interface AuthClaims {
  sub?: string;
  email?: string | null;
  fullName?: string | null;
  avatar?: string | null;
  roles?: string[];
  groups?: string[];
  isSuperuser?: boolean;
  isStaff?: boolean;
  iat?: number;
  exp?: number;
}

interface MockAuthConfigResponse {
  sub?: string;
  username?: string;
  email?: string | null;
  roles?: string[];
  groups?: string[];
  isSuperuser?: boolean;
  is_superuser?: boolean;
  isStaff?: boolean;
  is_staff?: boolean;
}

export interface LoginCredentials {
  username: string;
  password: string;
}

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly TOKEN_KEY = 'auth_token';
  private readonly REFRESH_KEY = 'auth_refresh_token';
  private readonly API_URL = '/api';
  private readonly MOCK_CLAIMS_URL = '/api/mock-auth-config/';

  private _token = signal<string | null>(null);
  private _claims = signal<AuthClaims | null>(null);
  private _mockClaims = signal<AuthClaims | null>(null);
  private _isLoading = signal(false);
  private _error = signal<string | null>(null);

  // Holds an in-flight refresh observable so concurrent requests wait for the same refresh
  private refreshRequest$: import('rxjs').Observable<string> | null = null;

  isAuthenticated = computed(() => {
    // Explicitly track config signal dependency
    const isMock = this.configService.config().MOCK_AUTH_ENABLED;
    const isMockEnabled = isMock === true || String(isMock).toLowerCase() === 'true';

    // If mock auth is enabled, we consider the app authenticated by default
    // to prevent race conditions during initialization and auto-login bypass.
    if (isMockEnabled) {
      return true;
    }

    const token = this.getToken();
    if (!token) return false;

    const claims = this.buildClaimsFromToken(token, isMockEnabled);
    if (!claims) return false;
    if (!claims.exp) return true; // token has no exp claim
    return Date.now() / 1000 < claims.exp;
  });
  claims = this._claims.asReadonly();
  isSuperuser = computed(() => this._claims()?.isSuperuser ?? false);
  isStaff = computed(() => this._claims()?.isStaff ?? false);
  isInAdminGroup = computed(() => {
    const groups = this._claims()?.groups ?? [];
    return groups.some((group) => String(group).toLowerCase() === 'admin');
  });
  isLoading = this._isLoading.asReadonly();
  error = this._error.asReadonly();

  constructor(
    private http: HttpClient,
    private router: Router,
    private configService: ConfigService,
    @Inject(PLATFORM_ID) private platformId: Object,
  ) {
    if (isPlatformBrowser(this.platformId)) {
      const stored = this.getStoredToken();
      this._token.set(stored);
      this._claims.set(this.buildClaimsFromToken(stored));
    }
  }

  /**
   * Initialize mock authentication - must be called AFTER config is loaded
   */
  initMockAuth(): void {
    if (!isPlatformBrowser(this.platformId) || !this.mockAuthEnabled) {
      return;
    }

    if (!this._token()) {
      this.setToken('mock-token');
    }

    if (this._token() === 'mock-token') {
      const fallback = this.buildFallbackMockClaims();
      this._mockClaims.set(fallback);
      this._claims.set(fallback);
      this.fetchMockClaims();
    }
  }

  private mockAuthEnabledSignal = computed(() => {
    const v = this.configService.config().MOCK_AUTH_ENABLED;
    if (typeof v === 'boolean') return v;
    if (typeof v === 'string') return v.toLowerCase() === 'true';
    return false;
  });

  private get mockAuthEnabled(): boolean {
    return this.mockAuthEnabledSignal();
  }

  login(credentials: LoginCredentials): Observable<AuthToken> {
    this._isLoading.set(true);
    this._error.set(null);

    // Short-circuit login for mock authentication
    if (this.mockAuthEnabled) {
      const fake = { token: 'mock-token', refresh: 'mock-refresh' } as AuthToken;
      const access = fake.token ?? fake.access ?? null;
      const refresh = fake.refresh ?? null;
      if (access) this.setToken(access);
      if (refresh) this.setRefreshToken(refresh);
      const fallback = this.buildFallbackMockClaims();
      this._mockClaims.set(fallback);
      this._claims.set(fallback);
      this.fetchMockClaims();
      this._isLoading.set(false);
      return of(fake);
    }

    return this.http.post<AuthToken>(`${this.API_URL}/api-token-auth/`, credentials).pipe(
      tap((response) => {
        const access = response.token ?? response.access ?? null;
        const refresh = response.refresh ?? null;
        if (access) this.setToken(access);
        if (refresh) this.setRefreshToken(refresh);
        this._claims.set(this.buildClaimsFromToken(access));
        this._isLoading.set(false);
      }),
      catchError((error) => {
        this._isLoading.set(false);
        this._error.set(error.error?.detail || 'Login failed');
        return throwError(() => error);
      }),
    );
  }

  logout(): void {
    const tokenAtLogout = this.getToken();

    // Clear local tokens and claims first to avoid recursive interceptor behavior
    this.clearToken();
    this.clearRefreshToken();
    this.router.navigate(['/login']);

    // If mock auth is enabled, there's no backend to record logout against
    if (this.mockAuthEnabled) {
      return;
    }

    // Attempt to record logout event in backend (best-effort).
    // Treat 401 (already logged out / unauthorized) as success and swallow it.
    const headers = tokenAtLogout ? new HttpHeaders({ Authorization: `Bearer ${tokenAtLogout}` }) : undefined;
    this.http
      .post(`${this.API_URL}/user-profile/logout/`, {}, { headers })
      .pipe(
        catchError((err) => {
          if (err?.status === 401) {
            // Ignore 401 responses — user is effectively logged out already
            return of(null);
          }
          // Log other errors so they can be investigated, but don't block logout flow
          console.error('Failed to record logout in backend', err);
          return throwError(() => err);
        }),
      )
      .subscribe({
        // No-op handlers: we've already handled logging above; keep subscription to fire the request
        next: () => {},
        error: () => {},
      });
  }

  private setToken(token: string): void {
    this._token.set(token);
    if (isPlatformBrowser(this.platformId)) {
      localStorage.setItem(this.TOKEN_KEY, token);
    }
  }

  private clearToken(): void {
    this._token.set(null);
    this._claims.set(null);
    if (isPlatformBrowser(this.platformId)) {
      localStorage.removeItem(this.TOKEN_KEY);
    }
  }

  private getStoredToken(): string | null {
    if (isPlatformBrowser(this.platformId)) {
      try {
        if (typeof localStorage?.getItem === 'function') {
          return localStorage.getItem(this.TOKEN_KEY);
        }
      } catch {
        return null;
      }
    }
    return null;
  }

  private setRefreshToken(refresh: string | null): void {
    if (isPlatformBrowser(this.platformId)) {
      if (refresh) localStorage.setItem(this.REFRESH_KEY, refresh);
      else localStorage.removeItem(this.REFRESH_KEY);
    }
  }

  private clearRefreshToken(): void {
    if (isPlatformBrowser(this.platformId)) {
      localStorage.removeItem(this.REFRESH_KEY);
    }
  }

  private getStoredRefreshToken(): string | null {
    if (isPlatformBrowser(this.platformId)) {
      try {
        if (typeof localStorage?.getItem === 'function') {
          return localStorage.getItem(this.REFRESH_KEY);
        }
      } catch {
        return null;
      }
    }
    return null;
  }

  getToken(): string | null {
    return this._token() ?? this.getStoredToken();
  }

  getRefreshToken(): string | null {
    return this.getStoredRefreshToken();
  }

  /**
   * Attempt to refresh the access token using the stored refresh token.
   * Ensures multiple concurrent callers share a single refresh call.
   */
  refreshToken(): Observable<string> {
    const existing = this.refreshRequest$;
    if (existing) return existing;

    // FIX: Prevent SSR crash - avoid accessing localStorage on server
    if (!isPlatformBrowser(this.platformId)) {
      // Return an error that can be caught or ignored, preventing the "No refresh token" crash
      return throwError(() => new Error('SSR: Cannot refresh token'));
    }

    const refresh = this.getRefreshToken();
    if (!refresh) {
      return throwError(() => new Error('No refresh token'));
    }

    const obs$ = this.http.post<AuthToken>(`${this.API_URL}/token/refresh/`, { refresh }).pipe(
      tap((response) => {
        const access = response.access ?? response.token ?? null;
        const newRefresh = response.refresh ?? null;
        if (!access) {
          throw new Error('No access token in refresh response');
        }
        this.setToken(access);
        if (newRefresh) this.setRefreshToken(newRefresh);
      }),
      map((resp: any) => (resp.access ?? resp.token) as string),
      finalize(() => {
        this.refreshRequest$ = null;
      }),
      shareReplay(1),
      catchError((err) => {
        // On refresh failure, clear tokens and forward error
        this.clearToken();
        this.clearRefreshToken();
        return throwError(() => err);
      }),
    );

    this.refreshRequest$ = obs$ as Observable<string>;
    return this.refreshRequest$;
  }

  /**
   * Update current claims. Useful when user updates their profile (e.g. avatar).
   */
  updateClaims(partialClaims: Partial<AuthClaims>): void {
    const current = this._claims();
    if (current) {
      this._claims.set({ ...current, ...partialClaims });
    }
  }

  private buildClaimsFromToken(token: string | null, isMockEnabled?: boolean): AuthClaims | null {
    if (!token) {
      return null;
    }

    // Use passed isMockEnabled or fall back to current config
    const mockEnabled = isMockEnabled ?? this.mockAuthEnabled;

    if (token === 'mock-token' && mockEnabled) {
      return this._mockClaims() ?? this.buildFallbackMockClaims();
    }

    const payload = this.decodeJwtPayload(token);
    if (!payload) {
      return null;
    }

    return {
      sub: payload['sub'],
      email: payload['email'] ?? null,
      fullName: payload['full_name'] ?? payload['fullName'] ?? null,
      avatar: payload['avatar'] ?? null,
      roles: payload['roles'] ?? payload['groups'] ?? [],
      groups: payload['groups'] ?? payload['roles'] ?? [],
      isSuperuser: payload['is_superuser'] ?? payload['isSuperuser'] ?? false,
      isStaff: payload['is_staff'] ?? payload['isStaff'] ?? false,
      iat: payload['iat'],
      exp: payload['exp'],
    } satisfies AuthClaims;
  }

  private buildFallbackMockClaims(): AuthClaims {
    return {
      sub: 'mock-user',
      email: 'mock@example.com',
      fullName: 'Mock User',
      roles: ['admin'],
      groups: ['admin'],
      isSuperuser: true,
      isStaff: true,
    };
  }

  private normalizeMockClaims(response: MockAuthConfigResponse): AuthClaims {
    return {
      sub: response.sub ?? response.username ?? 'mock-user',
      email: response.email ?? null,
      roles: response.roles ?? response.groups ?? [],
      groups: response.groups ?? response.roles ?? [],
      isSuperuser: response.isSuperuser ?? response.is_superuser ?? false,
      isStaff: response.isStaff ?? response.is_staff ?? false,
    } satisfies AuthClaims;
  }

  private fetchMockClaims(): void {
    if (!isPlatformBrowser(this.platformId) || !this.mockAuthEnabled) {
      return;
    }

    this.http
      .get<MockAuthConfigResponse>(this.MOCK_CLAIMS_URL)
      .pipe(
        tap((response) => {
          const claims = this.normalizeMockClaims(response);
          this._mockClaims.set(claims);
          this._claims.set(claims);
        }),
        catchError((error) => {
          const fallback = this.buildFallbackMockClaims();
          this._mockClaims.set(fallback);
          this._claims.set(fallback);
          return of(null);
        }),
      )
      .subscribe();
  }

  private decodeJwtPayload(token: string): Record<string, any> | null {
    try {
      const parts = token.split('.');
      if (parts.length < 2) {
        return null;
      }
      const payload = parts[1];
      const normalized = payload.replace(/-/g, '+').replace(/_/g, '/');
      const padded = normalized.padEnd(Math.ceil(normalized.length / 4) * 4, '=');
      if (!isPlatformBrowser(this.platformId)) {
        return null;
      }
      const decoded = atob(padded);
      return JSON.parse(decoded);
    } catch {
      return null;
    }
  }

  /**
   * Helpful during dev to know whether the service is running in mocked mode
   */
  isMockEnabled(): boolean {
    return !!this.mockAuthEnabled;
  }

  /**
   * Returns true if the provided token (or current token) is expired according to its `exp` claim.
   * If the token cannot be decoded or has no `exp` claim, the function returns false.
   */
  isTokenExpired(token?: string): boolean {
    const t = token ?? this.getToken();
    const claims = this.buildClaimsFromToken(t);
    if (!claims) return false;
    if (!claims.exp) return false;
    return Date.now() / 1000 >= claims.exp;
  }
}
