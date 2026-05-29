import { HttpBackend, HttpClient } from '@angular/common/http';
import { inject, Injectable } from '@angular/core';
import { catchError, firstValueFrom, of, timeout } from 'rxjs';

const BACKEND_READINESS_TIMEOUT_MS = 3_000;

interface FrontendHealthResponse {
  status?: string;
  backend?: string;
}

@Injectable({
  providedIn: 'root',
})
export class BackendReadinessService {
  private readonly http = new HttpClient(inject(HttpBackend));

  async isBackendReady(): Promise<boolean> {
    const response = await firstValueFrom(
      this.http.get<FrontendHealthResponse>('/backend-healthz').pipe(
        timeout(BACKEND_READINESS_TIMEOUT_MS),
        catchError(() => of<FrontendHealthResponse | null>(null)),
      ),
    );

    if (!response || typeof response !== 'object') {
      return false;
    }

    const status = String(response.status ?? '').toLowerCase();
    const backend = String(response.backend ?? '').toLowerCase();

    if (backend === 'reachable') {
      return true;
    }

    return status === 'ok' && backend !== 'unreachable' && backend !== 'unhealthy';
  }
}
