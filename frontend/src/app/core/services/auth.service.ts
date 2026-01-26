import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { computed, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, Observable, of, tap, throwError } from 'rxjs';

import { ConfigService } from './config.service';

export interface AuthToken {
  token: string;
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

  private _token = signal<string | null>(null);
  private _isLoading = signal(false);
  private _error = signal<string | null>(null);

  isAuthenticated = computed(() => !!this.getToken());
  isLoading = this._isLoading.asReadonly();
  error = this._error.asReadonly();

  constructor(
    private http: HttpClient,
    private router: Router,
    private configService: ConfigService,
    @Inject(PLATFORM_ID) private platformId: Object,
  ) {
    if (isPlatformBrowser(this.platformId)) {
      this._token.set(this.getStoredToken());
    }
  }

  /**
   * Initialize mock authentication - must be called AFTER config is loaded
   */
  initMockAuth(): void {
    if (isPlatformBrowser(this.platformId) && this.mockAuthEnabled && !this._token()) {
      this.setToken('mock-token');
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
      this._isLoading.set(false);
      return of(fake);
    }

    return this.http.post<AuthToken>(`${this.API_URL}/api-token-auth/`, credentials).pipe(
      tap((response) => {
        this.setToken(response.token);
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
    if (isPlatformBrowser(this.platformId)) {
      localStorage.removeItem(this.TOKEN_KEY);
    }
  }

  private getStoredToken(): string | null {
    if (isPlatformBrowser(this.platformId)) {
      return localStorage.getItem(this.TOKEN_KEY);
    }
    return null;
  }

  getToken(): string | null {
    return this._token() ?? this.getStoredToken();
  }

  /**
   * Helpful during dev to know whether the service is running in mocked mode
   */
  isMockEnabled(): boolean {
    return !!this.mockAuthEnabled;
  }
}
