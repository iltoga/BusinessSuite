import { inject, Injectable } from '@angular/core';
import { map, Observable } from 'rxjs';

import { DashboardStatsService } from '@/core/api/api/dashboard-stats.service';
import type { DashboardStats as DashboardStatsDto } from '@/core/api/model/dashboard-stats';

export type DashboardStats = DashboardStatsDto;

@Injectable({
  providedIn: 'root',
})
export class DashboardService {
  private readonly dashboardStatsApi = inject(DashboardStatsService);

  getStats(): Observable<DashboardStats> {
    return this.dashboardStatsApi.dashboardStatsList().pipe(
      map((response) => {
        if (Array.isArray(response)) {
          return response[0] ?? { customers: 0, applications: 0, invoices: 0 };
        }
        return (
          (response as DashboardStats | null) ?? { customers: 0, applications: 0, invoices: 0 }
        );
      }),
    );
  }
}
