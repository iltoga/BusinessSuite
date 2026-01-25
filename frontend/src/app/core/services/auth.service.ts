import { MOCK_AUTH_ENABLED } from '@/core/config/mock-auth.token';
import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { computed, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, Observable, of, tap, throwError } from 'rxjs';

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
    @Inject(PLATFORM_ID) private platformId: Object,
    @Inject(MOCK_AUTH_ENABLED) private mockAuthEnabled: boolean,
  ) {
    console.log('[AuthService] Mock auth enabled:', this.mockAuthEnabled);
    console.log(
      '[AuthService] Platform:',
      isPlatformBrowser(this.platformId) ? 'Browser' : 'Server',
    );

    if (isPlatformBrowser(this.platformId)) {
      this._token.set(this.getStoredToken());
      console.log('[AuthService] Existing token:', this._token());

      // If mock auth is enabled and there is no token, set a fake token so you don't have to login
      if (this.mockAuthEnabled && !this._token()) {
        console.log('[AuthService] Setting mock token');
        this.setToken('mock-token');
      }
    }
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
