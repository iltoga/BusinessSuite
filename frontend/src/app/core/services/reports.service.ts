import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

@Injectable({ providedIn: 'root' })
export class ReportsService {
  private http = inject(HttpClient);
  private authService = inject(AuthService);

  private headers() {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }

  getIndex(): Observable<{ reports: Array<{ name: string; description: string; url: string }> }> {
    return this.http
      .get<{ reports: Array<{ name: string; description: string; url: string }> }>(
        '/api/reports/',
        { headers: this.headers() },
      )
      .pipe(map((payload) => this.toSnakeCase(payload)));
  }

  getReport(slug: string, filters?: Record<string, string | number>): Observable<any> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        params = params.set(k, String(v));
      }
    }
    return this.http
      .get(`/api/reports/${slug}/`, { headers: this.headers(), params })
      .pipe(map((payload) => this.toSnakeCase(payload)));
  }

  private toSnakeCase<T>(value: T): T {
    if (Array.isArray(value)) {
      return value.map((item) => this.toSnakeCase(item)) as T;
    }

    if (!value || typeof value !== 'object') {
      return value;
    }

    const source = value as Record<string, unknown>;
    const normalized: Record<string, unknown> = {};

    Object.entries(source).forEach(([key, entryValue]) => {
      const snakeKey = key.replace(/([A-Z])/g, '_$1').toLowerCase();
      normalized[snakeKey] = this.toSnakeCase(entryValue);
    });

    return normalized as T;
  }
}
