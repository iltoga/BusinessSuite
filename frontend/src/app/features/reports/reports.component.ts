import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject, signal } from '@angular/core';
import { ActivatedRoute, RouterLink } from '@angular/router';
import type { ChartData } from 'chart.js';
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
  selectedYear = signal<number | null>(null);
  selectedMonth = signal<number | null>(null);

  chartColors = ['#0f766e', '#1d4ed8', '#b45309', '#dc2626', '#15803d', '#0ea5e9', '#475569'];

  reportTitle = computed(() => this.reportList().find((r) => r.url.includes(this.slug()))?.name || 'Reports');
  isAiCosting = computed(() => this.slug() === 'ai-costing');
  aiAvailableYears = computed<number[]>(() => this.data()?.available_years ?? []);

  constructor() {
    this.reportsService.getIndex().subscribe((res) => this.reportList.set(res.reports || []));
    this.route.paramMap.subscribe((params) => {
      this.slug.set(params.get('slug') || '');
      this.selectedYear.set(null);
      this.selectedMonth.set(null);
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
    const filters =
      this.slug() === 'ai-costing'
        ? {
            ...(this.selectedYear() ? { year: this.selectedYear()! } : {}),
            ...(this.selectedMonth() ? { month: this.selectedMonth()! } : {}),
          }
        : undefined;

    this.reportsService.getReport(this.slug(), filters).subscribe({
      next: (res) => {
        this.data.set(res);
        if (this.slug() === 'ai-costing') {
          this.selectedYear.set(res.selected_year ?? null);
          this.selectedMonth.set(res.selected_month ?? null);
        }
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  refreshAiCosting(): void {
    if (!this.isAiCosting()) return;
    this.loadReport();
  }

  onAiYearChange(event: Event): void {
    const value = Number((event.target as HTMLSelectElement).value);
    this.selectedYear.set(Number.isFinite(value) ? value : null);
    this.loadReport();
  }

  onAiMonthChange(event: Event): void {
    const value = Number((event.target as HTMLSelectElement).value);
    this.selectedMonth.set(Number.isFinite(value) ? value : null);
    this.loadReport();
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
      case 'productProfit':
        return { labels: d.product_data?.slice(0, 8).map((p: any) => p.name) ?? [], datasets: [{ label: 'Profit', data: d.product_data?.slice(0, 8).map((p: any) => p.total_profit) ?? [], backgroundColor: this.chartColors[4] }] };
      case 'productMargin':
        return { labels: d.product_data?.slice(0, 8).map((p: any) => p.name) ?? [], datasets: [{ label: 'Profit Margin %', data: d.product_data?.slice(0, 8).map((p: any) => p.profit_margin_percent) ?? [], backgroundColor: this.chartColors[2] }] };
      case 'profitMonthly':
        return { labels: d.monthly_profit_trends?.map((m: any) => m.label) ?? [], datasets: [{ label: 'Total Profit', data: d.monthly_profit_trends?.map((m: any) => m.total_profit) ?? [], borderColor: this.chartColors[1], backgroundColor: 'rgba(29, 78, 216, 0.12)', fill: true }] };
      case 'invoiceProfit':
        return { labels: d.invoice_profit_data?.slice(0, 10).map((i: any) => i.invoice_number) ?? [], datasets: [{ label: 'Profit per Invoice', data: d.invoice_profit_data?.slice(0, 10).map((i: any) => i.profit) ?? [], backgroundColor: this.chartColors[3] }] };
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
      case 'aiYearlyCost':
        return {
          labels: d.yearly_data?.map((row: any) => `${row.year}`) ?? [],
          datasets: [
            {
              label: 'Total Cost (USD)',
              data: d.yearly_data?.map((row: any) => row.total_cost) ?? [],
              borderColor: this.chartColors[0],
              backgroundColor: 'rgba(15, 118, 110, 0.14)',
              fill: true,
            },
          ],
        };
      case 'aiMonthlyCost':
        return {
          labels: d.monthly_data?.map((row: any) => row.label) ?? [],
          datasets: [
            {
              label: `Monthly Cost (${d.selected_year ?? ''})`,
              data: d.monthly_data?.map((row: any) => row.total_cost) ?? [],
              borderColor: this.chartColors[1],
              backgroundColor: 'rgba(29, 78, 216, 0.12)',
              fill: true,
            },
          ],
        };
      case 'aiMonthlyRequests':
        return {
          labels: d.monthly_data?.map((row: any) => row.label) ?? [],
          datasets: [
            {
              label: `Monthly Requests (${d.selected_year ?? ''})`,
              data: d.monthly_data?.map((row: any) => row.request_count) ?? [],
              backgroundColor: this.chartColors[2],
            },
          ],
        };
      case 'aiDailyCost':
        return {
          labels: d.daily_data?.map((row: any) => row.label) ?? [],
          datasets: [
            {
              label: `Daily Cost (${d.selected_month_label ?? ''})`,
              data: d.daily_data?.map((row: any) => row.total_cost) ?? [],
              borderColor: this.chartColors[3],
              backgroundColor: 'rgba(220, 38, 38, 0.1)',
              fill: true,
            },
          ],
        };
      case 'aiDailyRequests':
        return {
          labels: d.daily_data?.map((row: any) => row.label) ?? [],
          datasets: [
            {
              label: `Daily Requests (${d.selected_month_label ?? ''})`,
              data: d.daily_data?.map((row: any) => row.request_count) ?? [],
              borderColor: this.chartColors[4],
              backgroundColor: 'rgba(21, 128, 61, 0.11)',
              fill: true,
            },
          ],
        };
      case 'aiFeatureBreakdown':
        return {
          labels: d.feature_breakdown_month?.map((row: any) => row.feature) ?? [],
          datasets: [
            {
              label: 'Feature Cost (Selected Month)',
              data: d.feature_breakdown_month?.map((row: any) => row.total_cost) ?? [],
              backgroundColor: this.chartColors,
            },
          ],
        };
      default:
        return { labels: [], datasets: [] };
    }
  }

  monthOptions(): Array<{ value: number; label: string }> {
    return [
      { value: 1, label: 'January' },
      { value: 2, label: 'February' },
      { value: 3, label: 'March' },
      { value: 4, label: 'April' },
      { value: 5, label: 'May' },
      { value: 6, label: 'June' },
      { value: 7, label: 'July' },
      { value: 8, label: 'August' },
      { value: 9, label: 'September' },
      { value: 10, label: 'October' },
      { value: 11, label: 'November' },
      { value: 12, label: 'December' },
    ];
  }
}
