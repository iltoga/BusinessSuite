import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { computed, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, Observable, of, tap, throwError } from 'rxjs';

import { ConfigService } from './config.service';

export interface AuthToken {
  token: string;
}

export interface AuthClaims {
  sub?: string;
  email?: string | null;
  fullName?: string | null;
  avatar?: string | null;
  roles?: string[];
  groups?: string[];
  isSuperuser?: boolean;
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
  private readonly API_URL = '/api';
  private readonly MOCK_CLAIMS_URL = '/api/mock-auth-config/';

  private _token = signal<string | null>(null);
  private _claims = signal<AuthClaims | null>(null);
  private _mockClaims = signal<AuthClaims | null>(null);
  private _isLoading = signal(false);
  private _error = signal<string | null>(null);

  isAuthenticated = computed(() => !!this.getToken());
  claims = this._claims.asReadonly();
  isSuperuser = computed(() => this._claims()?.isSuperuser ?? false);
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

  private get mockAuthEnabled(): boolean {
    return this.configService.settings.mockAuthEnabled;
  }

  login(credentials: LoginCredentials): Observable<AuthToken> {
    this._isLoading.set(true);
    this._error.set(null);

    // Short-circuit login for mock authentication
    if (this.mockAuthEnabled) {
      const fake = { token: 'mock-token' } as AuthToken;
      this.setToken(fake.token);
      const fallback = this.buildFallbackMockClaims();
      this._mockClaims.set(fallback);
      this._claims.set(fallback);
      this.fetchMockClaims();
      this._isLoading.set(false);
      return of(fake);
    }

    return this.http.post<AuthToken>(`${this.API_URL}/api-token-auth/`, credentials).pipe(
      tap((response) => {
        this.setToken(response.token);
        this._claims.set(this.buildClaimsFromToken(response.token));
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
    // Record logout event in Django
    this.http.post(`${this.API_URL}/user-profile/logout/`, {}).subscribe({
      error: (err) => console.error('Failed to record logout in backend', err),
    });
    this.clearToken();
    this.router.navigate(['/login']);
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

  getToken(): string | null {
    return this._token() ?? this.getStoredToken();
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

  private buildClaimsFromToken(token: string | null): AuthClaims | null {
    if (!token) {
      return null;
    }

    if (token === 'mock-token' && this.mockAuthEnabled) {
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
    };
  }

  private normalizeMockClaims(response: MockAuthConfigResponse): AuthClaims {
    return {
      sub: response.sub ?? response.username ?? 'mock-user',
      email: response.email ?? null,
      roles: response.roles ?? response.groups ?? [],
      groups: response.groups ?? response.roles ?? [],
      isSuperuser: response.isSuperuser ?? response.is_superuser ?? false,
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
        catchError(() => {
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
}
