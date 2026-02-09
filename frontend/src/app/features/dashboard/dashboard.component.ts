import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  inject,
  OnInit,
  PLATFORM_ID,
  signal,
} from '@angular/core';

import { AuthService } from '@/core/services/auth.service';
import { DashboardService, DashboardStats } from '@/core/services/dashboard.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { CalendarIntegrationComponent } from '@/shared/components/calendar/calendar-integration.component';
import { ZardCardComponent } from '@/shared/components/card';
import { ContextHelpDirective } from '@/shared/directives';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [
    CommonModule,
    ZardButtonComponent,
    ZardCardComponent,
    ContextHelpDirective,
    CalendarIntegrationComponent,
  ],
  templateUrl: './dashboard.component.html',
  styleUrls: ['./dashboard.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardComponent implements OnInit {
  private authService = inject(AuthService);
  private dashboardService = inject(DashboardService);
  private platformId = inject(PLATFORM_ID);

  stats = signal<DashboardStats>({ customers: 0, applications: 0, invoices: 0 });

  ngOnInit(): void {
    if (!isPlatformBrowser(this.platformId)) {
      return;
    }

    this.dashboardService.getStats().subscribe({
      next: (data) => this.stats.set(data),
      error: (err) => console.error('Error fetching dashboard stats', err),
    });
  }

  logout(): void {
    this.authService.logout();
  }
}
