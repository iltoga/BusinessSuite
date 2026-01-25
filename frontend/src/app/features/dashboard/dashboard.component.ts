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
import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-dashboard',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ZardCardComponent],
  template: `
    <div class="space-y-6">
      <div class="flex items-center justify-between">
        <h1 class="text-2xl font-semibold">Dashboard</h1>
        <button z-button zType="outline" (click)="logout()">Logout</button>
      </div>

      <div class="grid gap-4 md:grid-cols-3">
        <z-card class="p-4">
          <div class="text-sm text-muted-foreground">Total Customers</div>
          <div class="text-3xl font-semibold">{{ stats().customers }}</div>
        </z-card>
        <z-card class="p-4">
          <div class="text-sm text-muted-foreground">Active Applications</div>
          <div class="text-3xl font-semibold">{{ stats().applications }}</div>
        </z-card>
        <z-card class="p-4">
          <div class="text-sm text-muted-foreground">Pending Invoices</div>
          <div class="text-3xl font-semibold">{{ stats().invoices }}</div>
        </z-card>
      </div>
    </div>
  `,
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
