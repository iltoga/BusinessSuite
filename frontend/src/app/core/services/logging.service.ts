import { AuthService } from '@/core/services/auth.service';
import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';

@Injectable({ providedIn: 'root' })
export class LoggingService {
  private endpoint = '/api/v1/observability/log/';

  constructor(
    private http: HttpClient,
    private auth: AuthService,
  ) {}

  sendLog(payload: any) {
    const claims = typeof this.auth.claims === 'function' ? this.auth.claims() : null;
    const enriched = {
      timestamp: new Date().toISOString(),
      metadata: {
        user: claims?.sub ?? null,
        userName: claims?.fullName ?? claims?.sub ?? null,
        ...payload.metadata,
      },
      level: payload.level || 'ERROR',
      message: payload.message || payload.message || String(payload),
      stack: payload.stack || null,
    };

    // fire-and-forget
    this.http.post(this.endpoint, enriched).subscribe({
      next: () => {},
      error: () => {
        // swallow errors to avoid interfering with app behavior
        // Could implement a retry/backoff queue here
      },
    });
  }
}
