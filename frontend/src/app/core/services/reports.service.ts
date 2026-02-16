import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable } from 'rxjs';

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
    return this.http.get<{ reports: Array<{ name: string; description: string; url: string }> }>(
      '/api/reports/',
      { headers: this.headers() },
    );
  }

  getReport(slug: string, filters?: Record<string, string | number>): Observable<any> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        params = params.set(k, String(v));
      }
    }
    return this.http.get(`/api/reports/${slug}/`, { headers: this.headers(), params });
  }
}
