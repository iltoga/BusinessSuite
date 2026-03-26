/**
 * AuthService — dual-mode JWT / mock authentication.
 *
 * ## Normal mode (JWT + refresh cookie)
 * Access tokens are kept only in memory. Refresh tokens are issued by the
 * backend as an HttpOnly cookie and refreshed through `/api/token/refresh/`.
 * The service restores the session during app initialization so reloads do
 * not depend on `localStorage`.
 *
 * ## Mock mode (`MOCK_AUTH_ENABLED`)
 * Mock auth stays dev-only. When enabled, the service returns a synthetic
 * token and claims without touching persistent browser storage.
 */
import { isPlatformBrowser } from '@angular/common';
import { HttpClient, HttpHeaders } from '@angular/common/http';
import { computed, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import {
  catchError,
  finalize,
  map,
  Observable,
  of,
  shareReplay,
  tap,
  throwError,
  timeout,
} from 'rxjs';

import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { unwrapApiRecord } from '@/core/utils/api-envelope';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';
import { ConfigService } from './config.service';

export interface AuthToken {
  access_token?: string;
  refresh_token?: string;
  token?: string;
  access?: string;
  refresh?: string;
  user?: AuthUserPayload | null;
  data?: AuthSessionPayload;
  meta?: Record<string, unknown>;
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

export interface AuthUserPayload {
  id?: number | string;
  username?: string;
  email?: string | null;
  full_name?: string | null;
  fullName?: string | null;
  avatar?: string | null;
  roles?: string[];
  groups?: string[];
  is_superuser?: boolean;
  isSuperuser?: boolean;
  is_staff?: boolean;
  isStaff?: boolean;
}

export interface AuthSessionPayload {
  access_token?: string;
  refresh_token?: string;
  token?: string;
  access?: string;
  refresh?: string;
  user?: AuthUserPayload | null;
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

const REFRESH_SESSION_HINT_COOKIE_NAME = 'bs_refresh_session_hint';
const LOGIN_REQUEST_TIMEOUT_MS = 15_000;
const REFRESH_REQUEST_TIMEOUT_MS = 8_000;

@Injectable({
  providedIn: 'root',
})
export class AuthService {
  private readonly API_URL = '/api';
  private readonly MOCK_CLAIMS_URL = '/api/mock-auth-config/';

  private _token = signal<string | null>(null);
  private _claims = signal<AuthClaims | null>(null);
  private _mockClaims = signal<AuthClaims | null>(null);
  private _isLoading = signal(false);
  private _error = signal<string | null>(null);
  readonly token = this._token.asReadonly();

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
    const adminName = (this.configService.config().rbac?.adminGroupName ?? 'admin').toLowerCase();
    return groups.some((group) => String(group).toLowerCase() === adminName);
  });
  isAdmin = computed(() => this.isSuperuser() || this.isInAdminGroup());
  isInManagerGroup = computed(() => {
    const groups = this._claims()?.groups ?? [];
    const managerName = (
      this.configService.config().rbac?.managerGroupName ?? 'manager'
    ).toLowerCase();
    return groups.some((group) => String(group).toLowerCase() === managerName);
  });
  isAdminOrManager = computed(
    () => this.isSuperuser() || this.isInAdmioGroup() || this.isInManagerGroup(),
  );
  isLoading = this._isLoading.asReadonly();
  error = this._error.asReadonly();

  constructor(
    private http: HttpClient,
    private router: Router,
    private configService: ConfigService,
    private desktopBridge: DesktopBridgeService,
    @Inject(PLATFORM_ID) private platformId: Object,
  ) {
    this.desktopBridge.publishAuthToken(null);
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
      const fake = {
        access_token: 'mock-token',
        refresh_token: 'mock-refresh',
        user: {
          id: 'mock-user',
          username: 'mock-user',
          email: 'mock@example.com',
          full_name: 'Mock User',
          roles: ['admin'],
          groups: ['admin'],
          is_superuser: true,
          is_staff: true,
        },
      } as AuthToken;
      const access = fake.access_token ?? fake.access ?? fake.token ?? null;
      if (access) this.setToken(access);
      this.applyAuthSession(fake);
      const fallback = this.buildFallbackMockClaims();
      this._mockClaims.set(fallback);
      this._claims.set(fallback);
      this.fetchMockClaims();
      this._isLoading.set(false);
      return of(fake);
    }

    return this.http
      .post<AuthToken>(`${this.API_URL}/api-token-auth/`, credentials, {
        withCredentials: true,
      })
      .pipe(
        timeout(LOGIN_REQUEST_TIMEOUT_MS),
        tap((response) => {
          this.applyAuthSession(response);
          this._isLoading.set(false);
        }),
        catchError((error) => {
          this._isLoading.set(false);
          this._error.set(this.extractErrorMessage(error) || 'Login failed');
          return throwError(() => error);
        }),
      );
  }

  logout(): void {
    const tokenAtLogout = this.getToken();

    // Clear local tokens and claims first to avoid recursive interceptor behavior
    this.clearToken();
    this.router.navigate(['/login']);

    // If mock auth is enabled, there's no backend to record logout against
    if (this.mockAuthEnabled) {
      return;
    }

    // Attempt to record logout event in backend (best-effort).
    // Treat 401 (already logged out / unauthorized) as success and swallow it.
    const headers = tokenAtLogout
      ? new HttpHeaders({ Authorization: `Bearer ${tokenAtLogout}` })
      : undefined;
    this.http
      .post(`${this.API_URL}/user-profile/logout/`, {}, { headers, withCredentials: true })
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
    this.desktopBridge.publishAuthToken(token);
  }

  private clearToken(): void {
    this._token.set(null);
    this._claims.set(null);
    this.desktopBridge.publishAuthToken(null);
  }

  getToken(): string | null {
    return this._token();
  }

  getRefreshToken(): string | null {
    return null;
  }

  restoreSession(): Observable<boolean> {
    if (!isPlatformBrowser(this.platformId) || this.mockAuthEnabled) {
      return of(false);
    }

    const token = this.getToken();
    if (token && !this.isTokenExpired(token)) {
      return of(true);
    }

    if (!this.hasRefreshSessionHint()) {
      return of(false);
    }

    return this.refreshToken().pipe(
      map(() => true),
      catchError(() => of(false)),
    );
  }

  /**
   * Attempt to refresh the access token using the stored refresh token.
   * Ensures multiple concurrent callers share a single refresh call.
   */
  refreshToken(): Observable<string> {
    const existing = this.refreshRequest$;
    if (existing) return existing;

    if (!isPlatformBrowser(this.platformId)) {
      return throwError(() => new Error('SSR: Cannot refresh token'));
    }

    if (this.mockAuthEnabled) {
      const mockToken = 'mock-token';
      this.setToken(mockToken);
      return of(mockToken);
    }

    const obs$ = this.http
      .post<AuthToken>(
        `${this.API_URL}/token/refresh/`,
        {},
        {
          withCredentials: true,
        },
      )
      .pipe(
        timeout(REFRESH_REQUEST_TIMEOUT_MS),
        tap((response) => {
          this.applyAuthSession(response);
        }),
        map((resp) => {
          const normalized = this.normalizeAuthSessionResponse(resp);
          const access = normalized.access_token ?? normalized.access ?? normalized.token ?? null;
          if (!access) {
            throw new Error('No access token in refresh response');
          }
          return access;
        }),
        finalize(() => {
          this.refreshRequest$ = null;
        }),
        shareReplay(1),
        catchError((err) => {
          this.clearToken();
          return throwError(() => err);
        }),
      );

    this.refreshRequest$ = obs$;
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

  private applyAuthSession(response: AuthToken | AuthSessionPayload | null | undefined): void {
    const session = this.normalizeAuthSessionResponse(response);
    const access = session.access_token ?? session.access ?? session.token ?? null;
    if (access) {
      this.setToken(access);
    } else {
      this.clearToken();
    }

    const userClaims = session.user ? this.buildClaimsFromUser(session.user) : null;
    const tokenClaims = access ? this.buildClaimsFromToken(access) : null;
    const claims = userClaims ?? tokenClaims;
    if (claims) {
      this._claims.set(claims);
    }
  }

  private normalizeAuthSessionResponse(
    response: AuthToken | AuthSessionPayload | null | undefined,
  ): AuthSessionPayload {
    if (!response || typeof response !== 'object') {
      return {};
    }

    const responseData = (response as { data?: AuthSessionPayload }).data;
    const session = (
      responseData && typeof responseData === 'object' ? responseData : response
    ) as AuthSessionPayload;
    return {
      access_token: session.access_token ?? session.access ?? session.token ?? undefined,
      refresh_token: session.refresh_token ?? session.refresh ?? undefined,
      token: session.token ?? session.access ?? session.access_token ?? undefined,
      access: session.access ?? session.access_token ?? session.token ?? undefined,
      refresh: session.refresh ?? session.refresh_token ?? undefined,
      user: session.user ?? undefined,
    };
  }

  private buildClaimsFromUser(user: AuthUserPayload): AuthClaims {
    const groups = user.groups ?? user.roles ?? [];
    const roles = user.roles ?? user.groups ?? [];
    const fullName = user.full_name ?? user.fullName ?? user.username ?? null;
    return {
      sub: String(user.id ?? user.username ?? ''),
      email: user.email ?? null,
      fullName,
      avatar: user.avatar ?? null,
      roles,
      groups,
      isSuperuser: user.is_superuser ?? user.isSuperuser ?? false,
      isStaff: user.is_staff ?? user.isStaff ?? false,
    };
  }

  private hasRefreshSessionHint(): boolean {
    if (!isPlatformBrowser(this.platformId)) {
      return false;
    }

    const cookieString = globalThis.document?.cookie ?? '';
    return cookieString.split(';').some((part) => {
      const trimmed = part.trim();
      return (
        trimmed === `${REFRESH_SESSION_HINT_COOKIE_NAME}=1` ||
        trimmed.startsWith(`${REFRESH_SESSION_HINT_COOKIE_NAME}=`)
      );
    });
  }

  private extractErrorMessage(error: any): string | null {
    return extractServerErrorMessage(error);
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

  private normalizeMockClaims(response: unknown): AuthClaims {
    const source = (unwrapApiRecord(response) ?? {}) as Record<string, unknown>;
    const toStringArray = (value: unknown): string[] =>
      Array.isArray(value) ? value.filter((item): item is string => typeof item === 'string') : [];

    const sub =
      typeof source['sub'] === 'string'
        ? source['sub']
        : typeof source['username'] === 'string'
          ? source['username']
          : 'mock-user';
    const email = typeof source['email'] === 'string' ? source['email'] : null;
    const roles = toStringArray(source['roles']);
    const groups = toStringArray(source['groups']);
    const isSuperuser = Boolean(source['isSuperuser'] ?? source['is_superuser'] ?? false);
    const isStaff = Boolean(source['isStaff'] ?? source['is_staff'] ?? false);
    return {
      sub,
      email,
      roles: roles.length ? roles : groups,
      groups: groups.length ? groups : roles,
      isSuperuser,
      isStaff,
    } satisfies AuthClaims;
  }

  private fetchMockClaims(): void {
    if (!isPlatformBrowser(this.platformId) || !this.mockAuthEnabled) {
      return;
    }

    this.http
      .get<unknown>(this.MOCK_CLAIMS_URL)
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
