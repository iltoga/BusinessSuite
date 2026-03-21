import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { DashboardStatsService } from '@/core/api/api/dashboard-stats.service';
import type { DashboardStats as DashboardStatsDto } from '@/core/api/model/dashboard-stats';
import { unwrapApiEnvelope } from '@/core/utils/api-envelope';

export type DashboardStats = DashboardStatsDto;

@Injectable({
  providedIn: 'root',
})
export class DashboardService {
  private readonly dashboardStatsApi = inject(DashboardStatsService);

  getStats(): Observable<DashboardStats> {
    return this.dashboardStatsApi.dashboardStatsList().pipe(
      map((response) => {
        const normalized = unwrapApiEnvelope<DashboardStats | DashboardStats[] | null>(response) as
          | DashboardStats
          | DashboardStats[]
          | null;

        if (Array.isArray(normalized)) {
          return normalized[0] ?? { customers: 0, applications: 0, invoices: 0 };
        }

        if (!normalized || typeof normalized !== 'object') {
          return { customers: 0, applications: 0, invoices: 0 };
        }

        return {
          customers: Number(normalized.customers ?? 0),
          applications: Number(normalized.applications ?? 0),
          invoices: Number(normalized.invoices ?? 0),
        };
      }),
    );
  }
}
