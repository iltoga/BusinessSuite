import { TestBed } from '@angular/core/testing';
import { firstValueFrom, of } from 'rxjs';

import { DashboardStatsService } from '@/core/api/api/dashboard-stats.service';

import { DashboardService } from './dashboard.service';

describe('DashboardService', () => {
  let service: DashboardService;
  let dashboardStatsApi: { dashboardStatsList: ReturnType<typeof vi.fn> };

  beforeEach(() => {
    dashboardStatsApi = {
      dashboardStatsList: vi.fn(),
    };

    TestBed.configureTestingModule({
      providers: [
        DashboardService,
        { provide: DashboardStatsService, useValue: dashboardStatsApi },
      ],
    });

    service = TestBed.inject(DashboardService);
  });

  it('unwraps success envelopes returned by the dashboard endpoint', async () => {
    dashboardStatsApi.dashboardStatsList.mockReturnValue(
      of({
        data: {
          customers: 12,
          applications: 7,
          invoices: 3,
        },
        meta: { apiVersion: 'v1' },
      }),
    );

    await expect(firstValueFrom(service.getStats())).resolves.toEqual({
      customers: 12,
      applications: 7,
      invoices: 3,
    });
  });

  it('falls back to zeroed stats when the payload is missing', async () => {
    dashboardStatsApi.dashboardStatsList.mockReturnValue(of({ data: null }));

    await expect(firstValueFrom(service.getStats())).resolves.toEqual({
      customers: 0,
      applications: 0,
      invoices: 0,
    });
  });
});
