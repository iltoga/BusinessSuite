import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import { ChartData } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';

import { ReportsService } from '@/core/services/reports.service';
import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-reports',
  standalone: true,
  imports: [CommonModule, RouterLink, BaseChartDirective, ZardCardComponent],
  templateUrl: './reports.component.html',
  styleUrls: ['./reports.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportsComponent {
  private route = inject(ActivatedRoute);
  private reportsService = inject(ReportsService);

  reportList = signal<Array<{ name: string; description: string; url: string }>>([]);
  slug = signal<string>('');
  data = signal<any>(null);
  loading = signal<boolean>(true);

  chartColors = ['#d97706', '#2563eb', '#10b981', '#ef4444', '#8b5cf6', '#14b8a6', '#f59e0b'];

  reportTitle = computed(() => this.reportList().find((r) => r.url.includes(this.slug()))?.name || 'Reports');

  constructor() {
    this.reportsService.getIndex().subscribe((res) => this.reportList.set(res.reports || []));
    this.route.paramMap.subscribe((params) => {
      this.slug.set(params.get('slug') || '');
      this.loadReport();
    });
  }

  private loadReport() {
    this.loading.set(true);
    if (!this.slug()) {
      this.data.set(null);
      this.loading.set(false);
      return;
    }
    this.reportsService.getReport(this.slug()).subscribe({
      next: (res) => {
        this.data.set(res);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  chart(type: string): ChartData<any> {
    const d = this.data();
    if (!d) return { labels: [], datasets: [] };

    switch (type) {
      case 'revenueMonthly':
        return {
          labels: d.monthly_revenue?.map((m: any) => m.label) ?? [],
          datasets: [
            { label: 'Invoiced', data: d.monthly_revenue?.map((m: any) => m.invoiced) ?? [], backgroundColor: this.chartColors[0] },
            { label: 'Paid', data: d.monthly_revenue?.map((m: any) => m.paid) ?? [], backgroundColor: this.chartColors[1] },
          ],
        };
      case 'kpiRevenue':
        return { labels: d.chart_data?.map((c: any) => c.label) ?? [], datasets: [{ label: 'Revenue', data: d.chart_data?.map((c: any) => c.revenue) ?? [], borderColor: this.chartColors[0], backgroundColor: 'rgba(217,119,6,.2)', fill: true }] };
      case 'statusCounts':
        return { labels: d.status_data?.map((s: any) => s.status) ?? [], datasets: [{ data: d.status_data?.map((s: any) => s.count) ?? [], backgroundColor: this.chartColors }] };
      case 'aging':
        return { labels: d.aging_data?.map((a: any) => a.label) ?? [], datasets: [{ label: 'Outstanding', data: d.aging_data?.map((a: any) => a.total) ?? [], backgroundColor: this.chartColors[3] }] };
      case 'ltvTop':
        return { labels: d.top_customers?.map((c: any) => c.customer_name) ?? [], datasets: [{ label: 'Revenue', data: d.top_customers?.map((c: any) => c.total_revenue) ?? [], backgroundColor: this.chartColors[4] }] };
      case 'ltvSegment':
        return { labels: ['High Value', 'Medium Value', 'Low Value'], datasets: [{ data: [d.high_value_count ?? 0, d.medium_value_count ?? 0, d.low_value_count ?? 0], backgroundColor: [this.chartColors[2], this.chartColors[0], this.chartColors[1]] }] };
      case 'productRevenue':
        return { labels: d.product_data?.slice(0, 8).map((p: any) => p.name) ?? [], datasets: [{ label: 'Revenue', data: d.product_data?.slice(0, 8).map((p: any) => p.total_revenue) ?? [], backgroundColor: this.chartColors[0] }] };
      case 'typeRevenue':
        return { labels: d.type_data?.map((t: any) => t.type) ?? [], datasets: [{ data: d.type_data?.map((t: any) => t.revenue) ?? [], backgroundColor: this.chartColors }] };
      case 'cashflowMonthly':
        return { labels: d.monthly_cashflow?.map((m: any) => m.label) ?? [], datasets: [{ label: 'Cashflow', data: d.monthly_cashflow?.map((m: any) => m.total) ?? [], borderColor: this.chartColors[2] }] };
      case 'paymentTypes':
        return { labels: d.payment_type_data?.map((m: any) => m.type) ?? [], datasets: [{ label: 'Total', data: d.payment_type_data?.map((m: any) => m.total) ?? [], backgroundColor: this.chartColors }] };
      case 'processingTime':
        return { labels: d.processing_time_data?.map((p: any) => p.product) ?? [], datasets: [{ label: 'Avg Days', data: d.processing_time_data?.map((p: any) => p.avg_days) ?? [], backgroundColor: this.chartColors[3] }] };
      case 'demandTotal':
        return { labels: d.total_by_month?.map((m: any) => m.label) ?? [], datasets: [{ label: 'Total Applications', data: d.total_by_month?.map((m: any) => m.count) ?? [], borderColor: this.chartColors[1] }] };
      case 'demandGrowth':
        return { labels: Object.keys(d.growth_rates ?? {}), datasets: [{ label: 'Growth %', data: Object.values(d.growth_rates ?? {}), backgroundColor: this.chartColors[4] }] };
      case 'kpiCustomers':
        return { labels: d.top_customers?.map((c: any) => c.name) ?? [], datasets: [{ label: 'Revenue', data: d.top_customers?.map((c: any) => c.total_revenue) ?? [], backgroundColor: this.chartColors[1] }] };
      default:
        return { labels: [], datasets: [] };
    }
  }
}
