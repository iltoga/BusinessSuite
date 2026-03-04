import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  DestroyRef,
  computed,
  inject,
  signal,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { ActivatedRoute, RouterLink } from '@angular/router';
import type { ChartData } from 'chart.js';
import { BaseChartDirective } from 'ng2-charts';
import { Subject, catchError, map, of, switchMap } from 'rxjs';

import {
  ReportsIndexItemDto,
  ReportsPayloadDto,
  ReportsService,
} from '@/core/services/reports.service';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardTableComponent } from '@/shared/components/table';

type ReportChartType =
  | 'revenueMonthly'
  | 'kpiRevenue'
  | 'statusCounts'
  | 'aging'
  | 'ltvTop'
  | 'ltvSegment'
  | 'productRevenue'
  | 'productProfit'
  | 'productMargin'
  | 'profitMonthly'
  | 'invoiceProfit'
  | 'typeRevenue'
  | 'cashflowMonthly'
  | 'paymentTypes'
  | 'processingTime'
  | 'demandTotal'
  | 'demandGrowth'
  | 'kpiCustomers'
  | 'aiYearlyCost'
  | 'aiMonthlyCost'
  | 'aiMonthlyRequests'
  | 'aiDailyCost'
  | 'aiDailyRequests'
  | 'aiFeatureBreakdown'
  | 'aiModelBreakdownCost'
  | 'aiModelBreakdownRequests';

type ReportChartData = ChartData<'bar' | 'line' | 'pie' | 'doughnut'>;

const EMPTY_CHART_DATA: ReportChartData = { labels: [], datasets: [] };

const REPORT_MONTH_OPTIONS: ReadonlyArray<{ value: number; label: string }> = [
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

const CHART_TYPES_BY_SLUG = {
  'ai-costing': [
    'aiYearlyCost',
    'aiMonthlyCost',
    'aiMonthlyRequests',
    'aiFeatureBreakdown',
    'aiModelBreakdownCost',
    'aiModelBreakdownRequests',
    'aiDailyCost',
    'aiDailyRequests',
  ],
  revenue: ['revenueMonthly'],
  'kpi-dashboard': ['kpiRevenue', 'kpiCustomers'],
  'invoice-status': ['statusCounts', 'aging'],
  'customer-ltv': ['ltvTop', 'ltvSegment'],
  'product-revenue': [
    'productRevenue',
    'productProfit',
    'profitMonthly',
    'productMargin',
    'invoiceProfit',
    'typeRevenue',
  ],
  'cash-flow': ['cashflowMonthly', 'paymentTypes'],
  'application-pipeline': ['statusCounts', 'processingTime'],
  'product-demand': ['demandTotal', 'demandGrowth'],
} as const satisfies Record<string, readonly ReportChartType[]>;

@Component({
  selector: 'app-reports',
  standalone: true,
  imports: [
    CommonModule,
    RouterLink,
    BaseChartDirective,
    ZardButtonComponent,
    ZardCardComponent,
    ZardTableComponent,
  ],
  templateUrl: './reports.component.html',
  styleUrls: ['./reports.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ReportsComponent {
  private route = inject(ActivatedRoute);
  private reportsService = inject(ReportsService);
  private readonly destroyRef = inject(DestroyRef);
  private readonly reportLoadTrigger$ = new Subject<void>();

  reportList = signal<ReportsIndexItemDto[]>([]);
  slug = signal<string>('');
  data = signal<ReportsPayloadDto | null>(null);
  loading = signal<boolean>(true);
  selectedYear = signal<number | null>(null);
  selectedMonth = signal<number | null>(null);

  chartColors = ['#0f766e', '#1d4ed8', '#b45309', '#dc2626', '#15803d', '#0ea5e9', '#475569'];

  reportTitle = computed(() => this.reportList().find((r) => r.url.includes(this.slug()))?.name || 'Reports');
  isAiCosting = computed(() => this.slug() === 'ai-costing');
  aiAvailableYears = computed<number[]>(() => this.data()?.available_years ?? []);
  readonly monthOptions = REPORT_MONTH_OPTIONS;
  readonly chartDataByType = computed<Partial<Record<ReportChartType, ReportChartData>>>(() => {
    const d = this.data();
    if (!d) {
      return {};
    }

    const slug = this.slug();
    const chartTypes = CHART_TYPES_BY_SLUG[slug as keyof typeof CHART_TYPES_BY_SLUG] ?? [];
    const result: Partial<Record<ReportChartType, ReportChartData>> = {};
    for (const chartType of chartTypes) {
      result[chartType] = this.buildChartData(chartType, d);
    }
    return result;
  });

  constructor() {
    of(null)
      .pipe(
        switchMap(() => this.reportsService.getIndex()),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((res) => this.reportList.set(res.reports || []));

    this.reportLoadTrigger$
      .pipe(
        switchMap(() => {
          this.loading.set(true);
          const slug = this.slug();
          if (!slug) {
            return of({ kind: 'empty' as const });
          }

          const selectedYear = this.selectedYear();
          const selectedMonth = this.selectedMonth();
          const filters =
            slug === 'ai-costing'
              ? {
                  ...(selectedYear !== null ? { year: selectedYear } : {}),
                  ...(selectedMonth !== null ? { month: selectedMonth } : {}),
                }
              : undefined;

          return this.reportsService.getReport(slug, filters).pipe(
            map((res) => ({ kind: 'success' as const, slug, res })),
            catchError(() => of({ kind: 'error' as const })),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((result) => {
        if (result.kind === 'success') {
          this.data.set(result.res);
          if (result.slug === 'ai-costing') {
            this.selectedYear.set(result.res.selected_year ?? null);
            this.selectedMonth.set(result.res.selected_month ?? null);
          }
        } else if (result.kind === 'empty') {
          this.data.set(null);
        }
        this.loading.set(false);
      });

    this.route.paramMap.pipe(takeUntilDestroyed(this.destroyRef)).subscribe((params) => {
      this.slug.set(params.get('slug') || '');
      this.selectedYear.set(null);
      this.selectedMonth.set(null);
      this.loadReport();
    });
  }

  private loadReport(): void {
    this.reportLoadTrigger$.next();
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

  chart(type: ReportChartType): ReportChartData {
    return this.chartDataByType()[type] ?? EMPTY_CHART_DATA;
  }

  private buildChartData(type: ReportChartType, d: ReportsPayloadDto): ReportChartData {
    switch (type) {
      case 'revenueMonthly':
        return {
          labels: d.monthly_revenue.map((m) => m.label),
          datasets: [
            {
              label: 'Invoiced',
              data: d.monthly_revenue.map((m) => m.invoiced),
              backgroundColor: this.chartColors[0],
            },
            {
              label: 'Paid',
              data: d.monthly_revenue.map((m) => m.paid),
              backgroundColor: this.chartColors[1],
            },
          ],
        };
      case 'kpiRevenue':
        return {
          labels: d.chart_data.map((c) => c.label),
          datasets: [
            {
              label: 'Revenue',
              data: d.chart_data.map((c) => c.revenue),
              borderColor: this.chartColors[0],
              backgroundColor: 'rgba(217,119,6,.2)',
              fill: true,
            },
          ],
        };
      case 'statusCounts':
        return {
          labels: d.status_data.map((s) => s.status),
          datasets: [{ data: d.status_data.map((s) => s.count), backgroundColor: this.chartColors }],
        };
      case 'aging':
        return {
          labels: d.aging_data.map((a) => a.label),
          datasets: [
            {
              label: 'Outstanding',
              data: d.aging_data.map((a) => a.total),
              backgroundColor: this.chartColors[3],
            },
          ],
        };
      case 'ltvTop':
        return {
          labels: d.top_customers.map((c) => c.customer_name),
          datasets: [
            {
              label: 'Revenue',
              data: d.top_customers.map((c) => c.total_revenue),
              backgroundColor: this.chartColors[4],
            },
          ],
        };
      case 'ltvSegment':
        return {
          labels: ['High Value', 'Medium Value', 'Low Value'],
          datasets: [
            {
              data: [d.high_value_count ?? 0, d.medium_value_count ?? 0, d.low_value_count ?? 0],
              backgroundColor: [this.chartColors[2], this.chartColors[0], this.chartColors[1]],
            },
          ],
        };
      case 'productRevenue':
        return {
          labels: d.product_data.slice(0, 8).map((p) => p.name),
          datasets: [
            {
              label: 'Revenue',
              data: d.product_data.slice(0, 8).map((p) => p.total_revenue),
              backgroundColor: this.chartColors[0],
            },
          ],
        };
      case 'productProfit':
        return {
          labels: d.product_data.slice(0, 8).map((p) => p.name),
          datasets: [
            {
              label: 'Profit',
              data: d.product_data.slice(0, 8).map((p) => p.total_profit),
              backgroundColor: this.chartColors[4],
            },
          ],
        };
      case 'productMargin':
        return {
          labels: d.product_data.slice(0, 8).map((p) => p.name),
          datasets: [
            {
              label: 'Profit Margin %',
              data: d.product_data.slice(0, 8).map((p) => p.profit_margin_percent),
              backgroundColor: this.chartColors[2],
            },
          ],
        };
      case 'profitMonthly':
        return {
          labels: d.monthly_profit_trends.map((m) => m.label),
          datasets: [
            {
              label: 'Total Profit',
              data: d.monthly_profit_trends.map((m) => m.total_profit),
              borderColor: this.chartColors[1],
              backgroundColor: 'rgba(29, 78, 216, 0.12)',
              fill: true,
            },
          ],
        };
      case 'invoiceProfit':
        return {
          labels: d.invoice_profit_data.slice(0, 10).map((i) => i.invoice_number),
          datasets: [
            {
              label: 'Profit per Invoice',
              data: d.invoice_profit_data.slice(0, 10).map((i) => i.profit),
              backgroundColor: this.chartColors[3],
            },
          ],
        };
      case 'typeRevenue':
        return {
          labels: d.type_data.map((t) => t.type),
          datasets: [{ data: d.type_data.map((t) => t.revenue), backgroundColor: this.chartColors }],
        };
      case 'cashflowMonthly':
        return {
          labels: d.monthly_cashflow.map((m) => m.label),
          datasets: [
            {
              label: 'Cashflow',
              data: d.monthly_cashflow.map((m) => m.total),
              borderColor: this.chartColors[2],
            },
          ],
        };
      case 'paymentTypes':
        return {
          labels: d.payment_type_data.map((m) => m.type),
          datasets: [
            {
              label: 'Total',
              data: d.payment_type_data.map((m) => m.total),
              backgroundColor: this.chartColors,
            },
          ],
        };
      case 'processingTime':
        return {
          labels: d.processing_time_data.map((p) => p.product),
          datasets: [
            {
              label: 'Avg Days',
              data: d.processing_time_data.map((p) => p.avg_days),
              backgroundColor: this.chartColors[3],
            },
          ],
        };
      case 'demandTotal':
        return {
          labels: d.total_by_month.map((m) => m.label),
          datasets: [
            {
              label: 'Total Applications',
              data: d.total_by_month.map((m) => m.count),
              borderColor: this.chartColors[1],
            },
          ],
        };
      case 'demandGrowth':
        return {
          labels: Object.keys(d.growth_rates),
          datasets: [
            {
              label: 'Growth %',
              data: Object.values(d.growth_rates),
              backgroundColor: this.chartColors[4],
            },
          ],
        };
      case 'kpiCustomers':
        return {
          labels: d.top_customers.map((c) => c.name),
          datasets: [
            {
              label: 'Revenue',
              data: d.top_customers.map((c) => c.total_revenue),
              backgroundColor: this.chartColors[1],
            },
          ],
        };
      case 'aiYearlyCost':
        return {
          labels: d.yearly_data.map((row) => `${row.year}`),
          datasets: [
            {
              label: 'Total Cost (USD)',
              data: d.yearly_data.map((row) => row.total_cost),
              borderColor: this.chartColors[0],
              backgroundColor: 'rgba(15, 118, 110, 0.14)',
              fill: true,
            },
          ],
        };
      case 'aiMonthlyCost':
        return {
          labels: d.monthly_data.map((row) => row.label),
          datasets: [
            {
              label: `Monthly Cost (${d.selected_year ?? ''})`,
              data: d.monthly_data.map((row) => row.total_cost),
              borderColor: this.chartColors[1],
              backgroundColor: 'rgba(29, 78, 216, 0.12)',
              fill: true,
            },
          ],
        };
      case 'aiMonthlyRequests':
        return {
          labels: d.monthly_data.map((row) => row.label),
          datasets: [
            {
              label: `Monthly Requests (${d.selected_year ?? ''})`,
              data: d.monthly_data.map((row) => row.request_count),
              backgroundColor: this.chartColors[2],
            },
          ],
        };
      case 'aiDailyCost':
        return {
          labels: d.daily_data.map((row) => row.label),
          datasets: [
            {
              label: `Daily Cost (${d.selected_month_label ?? ''})`,
              data: d.daily_data.map((row) => row.total_cost),
              borderColor: this.chartColors[3],
              backgroundColor: 'rgba(220, 38, 38, 0.1)',
              fill: true,
            },
          ],
        };
      case 'aiDailyRequests':
        return {
          labels: d.daily_data.map((row) => row.label),
          datasets: [
            {
              label: `Daily Requests (${d.selected_month_label ?? ''})`,
              data: d.daily_data.map((row) => row.request_count),
              borderColor: this.chartColors[4],
              backgroundColor: 'rgba(21, 128, 61, 0.11)',
              fill: true,
            },
          ],
        };
      case 'aiFeatureBreakdown':
        return {
          labels: d.feature_breakdown_month.map((row) => row.feature),
          datasets: [
            {
              label: 'Feature Cost (Selected Month)',
              data: d.feature_breakdown_month.map((row) => row.total_cost),
              backgroundColor: this.chartColors,
            },
          ],
        };
      case 'aiModelBreakdownCost':
        return {
          labels: d.model_breakdown_month.map((row) => row.model),
          datasets: [
            {
              label: 'Model Cost (Selected Month)',
              data: d.model_breakdown_month.map((row) => row.total_cost),
              backgroundColor: this.chartColors,
            },
          ],
        };
      case 'aiModelBreakdownRequests':
        return {
          labels: d.model_breakdown_month.map((row) => row.model),
          datasets: [
            {
              label: 'Model Requests (Selected Month)',
              data: d.model_breakdown_month.map((row) => row.request_count),
              backgroundColor: this.chartColors,
            },
          ],
        };
    }
  }
}
