import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { computed, Inject, Injectable, PLATFORM_ID, signal } from '@angular/core';
import { Router } from '@angular/router';
import { catchError, Observable, tap, throwError } from 'rxjs';

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
  ) {
    if (isPlatformBrowser(this.platformId)) {
      this._token.set(this.getStoredToken());
    }
  }

  login(credentials: LoginCredentials): Observable<AuthToken> {
    this._isLoading.set(true);
    this._error.set(null);

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
}
