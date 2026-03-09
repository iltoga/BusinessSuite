import { HttpClient, HttpHeaders, HttpParams } from '@angular/common/http';
import { Injectable, inject } from '@angular/core';
import { Observable, map } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';

export interface ReportsIndexItemDto {
  name: string;
  description: string;
  url: string;
}

export interface ReportsIndexDto {
  reports: ReportsIndexItemDto[];
}

export interface ReportMonthlyRevenueRowDto {
  label: string;
  invoiced: number;
  paid: number;
}

export interface ReportChartRevenueRowDto {
  label: string;
  revenue: number;
}

export interface ReportStatusRowDto {
  status: string;
  count: number;
}

export interface ReportAgingRowDto {
  label: string;
  total: number;
}

export interface ReportTopCustomerRowDto {
  customer_name: string;
  name: string;
  total_revenue: number;
}

export interface ReportProductRowDto {
  name: string;
  total_revenue: number;
  total_profit: number;
  profit_margin_percent: number;
  base_price_formatted?: string;
  retail_price_formatted?: string;
  unit_profit_formatted?: string;
  total_revenue_formatted?: string;
  total_profit_formatted?: string;
}

export interface ReportInvoiceProfitRowDto {
  invoice_number: string;
  customer_name: string;
  invoice_date: string;
  total_amount_formatted?: string;
  profit_formatted?: string;
  profit_margin_percent: number;
  profit: number;
}

export interface ReportTypeRevenueRowDto {
  type: string;
  revenue: number;
}

export interface ReportCashflowRowDto {
  label: string;
  total: number;
}

export interface ReportPaymentTypeRowDto {
  type: string;
  total: number;
}

export interface ReportProcessingTimeRowDto {
  product: string;
  avg_days: number;
}

export interface ReportDemandTotalRowDto {
  label: string;
  count: number;
}

export interface ReportYearlyCostRowDto {
  year: number;
  total_cost: number;
}

export interface ReportMonthlyCostRowDto {
  label: string;
  total_cost: number;
  request_count: number;
}

export interface ReportFeatureBreakdownRowDto {
  feature: string;
  request_count: number;
  success_count: number;
  failed_count: number;
  total_tokens: number;
  total_cost: number;
}

export interface ReportModelBreakdownRowDto {
  model: string;
  request_count: number;
  success_count: number;
  failed_count: number;
  total_tokens: number;
  total_cost: number;
}

export interface ReportMonthlyInvoiceRowDto {
  invoice_number: string;
  customer_name: string;
  invoice_date: string;
  total_amount_formatted?: string;
  total_due_formatted?: string;
}

export interface ReportPeriodSummaryDto {
  total_cost: number;
  request_count: number;
}

export interface ReportsPayloadDto {
  [key: string]: unknown;
  available_years: number[];
  selected_year: number | null;
  selected_month: number | null;
  selected_month_label: string;
  high_value_count?: number;
  medium_value_count?: number;
  low_value_count?: number;
  year_summary?: ReportPeriodSummaryDto;
  month_summary?: ReportPeriodSummaryDto;
  monthly_revenue: ReportMonthlyRevenueRowDto[];
  chart_data: ReportChartRevenueRowDto[];
  status_data: ReportStatusRowDto[];
  aging_data: ReportAgingRowDto[];
  top_customers: ReportTopCustomerRowDto[];
  product_data: ReportProductRowDto[];
  monthly_profit_trends: Array<{ label: string; total_profit: number }>;
  invoice_profit_data: ReportInvoiceProfitRowDto[];
  type_data: ReportTypeRevenueRowDto[];
  monthly_cashflow: ReportCashflowRowDto[];
  payment_type_data: ReportPaymentTypeRowDto[];
  processing_time_data: ReportProcessingTimeRowDto[];
  total_by_month: ReportDemandTotalRowDto[];
  growth_rates: Record<string, number>;
  yearly_data: ReportYearlyCostRowDto[];
  monthly_data: ReportMonthlyCostRowDto[];
  daily_data: ReportMonthlyCostRowDto[];
  feature_breakdown_month: ReportFeatureBreakdownRowDto[];
  model_breakdown_month: ReportModelBreakdownRowDto[];
  invoices: ReportMonthlyInvoiceRowDto[];
  total_invoiced_formatted?: string;
  total_paid_formatted?: string;
  total_outstanding_formatted?: string;
  total_cashflow_formatted?: string;
  total_revenue_formatted?: string;
  total_profit_formatted?: string;
  overall_profit_margin_percent?: number;
  total_applications?: number;
}

@Injectable({ providedIn: 'root' })
export class ReportsService {
  private http = inject(HttpClient);
  private authService = inject(AuthService);

  private headers(): HttpHeaders | undefined {
    const token = this.authService.getToken();
    return token ? new HttpHeaders({ Authorization: `Bearer ${token}` }) : undefined;
  }

  getIndex(): Observable<ReportsIndexDto> {
    return this.http
      .get<unknown>('/api/reports/', { headers: this.headers() })
      .pipe(map((payload) => this.adaptReportsIndex(payload)));
  }

  getReport(slug: string, filters?: Record<string, string | number>): Observable<ReportsPayloadDto> {
    let params = new HttpParams();
    if (filters) {
      for (const [k, v] of Object.entries(filters)) {
        params = params.set(k, String(v));
      }
    }
    return this.http
      .get<unknown>(`/api/reports/${slug}/`, { headers: this.headers(), params })
      .pipe(map((payload) => this.adaptReportPayload(payload)));
  }

  private adaptReportsIndex(payload: unknown): ReportsIndexDto {
    const source = this.asRecord(this.normalizeToSnakeCase(payload));
    const reports = this.mapArray(source['reports'], (item) => ({
      name: this.toOptionalString(item['name']) ?? '',
      description: this.toOptionalString(item['description']) ?? '',
      url: this.toOptionalString(item['url']) ?? '',
    }));
    return { reports };
  }

  private adaptReportPayload(payload: unknown): ReportsPayloadDto {
    const source = this.asRecord(this.normalizeToSnakeCase(payload));
    const normalized: ReportsPayloadDto = {
      ...source,
      available_years: this.toNumberArray(source['available_years']),
      selected_year: this.toNullableNumber(source['selected_year']),
      selected_month: this.toNullableNumber(source['selected_month']),
      selected_month_label: this.toOptionalString(source['selected_month_label']) ?? '',
      high_value_count: this.toOptionalNumber(source['high_value_count']),
      medium_value_count: this.toOptionalNumber(source['medium_value_count']),
      low_value_count: this.toOptionalNumber(source['low_value_count']),
      year_summary: this.adaptPeriodSummary(source['year_summary']),
      month_summary: this.adaptPeriodSummary(source['month_summary']),
      monthly_revenue: this.mapArray(source['monthly_revenue'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        invoiced: this.toNumber(item['invoiced']),
        paid: this.toNumber(item['paid']),
      })),
      chart_data: this.mapArray(source['chart_data'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        revenue: this.toNumber(item['revenue']),
      })),
      status_data: this.mapArray(source['status_data'], (item) => ({
        status: this.toOptionalString(item['status']) ?? '',
        count: this.toNumber(item['count']),
      })),
      aging_data: this.mapArray(source['aging_data'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        total: this.toNumber(item['total']),
      })),
      top_customers: this.mapArray(source['top_customers'], (item) => {
        const label =
          this.toOptionalString(item['customer_name']) ?? this.toOptionalString(item['name']) ?? '';
        return {
          customer_name: label,
          name: this.toOptionalString(item['name']) ?? label,
          total_revenue: this.toNumber(item['total_revenue']),
        };
      }),
      product_data: this.mapArray(source['product_data'], (item) => ({
        name: this.toOptionalString(item['name']) ?? '',
        total_revenue: this.toNumber(item['total_revenue']),
        total_profit: this.toNumber(item['total_profit']),
        profit_margin_percent: this.toNumber(item['profit_margin_percent']),
        base_price_formatted: this.toOptionalString(item['base_price_formatted']),
        retail_price_formatted: this.toOptionalString(item['retail_price_formatted']),
        unit_profit_formatted: this.toOptionalString(item['unit_profit_formatted']),
        total_revenue_formatted: this.toOptionalString(item['total_revenue_formatted']),
        total_profit_formatted: this.toOptionalString(item['total_profit_formatted']),
      })),
      monthly_profit_trends: this.mapArray(source['monthly_profit_trends'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        total_profit: this.toNumber(item['total_profit']),
      })),
      invoice_profit_data: this.mapArray(source['invoice_profit_data'], (item) => ({
        invoice_number: this.toOptionalString(item['invoice_number']) ?? '',
        customer_name: this.toOptionalString(item['customer_name']) ?? '',
        invoice_date: this.toOptionalString(item['invoice_date']) ?? '',
        total_amount_formatted: this.toOptionalString(item['total_amount_formatted']),
        profit_formatted: this.toOptionalString(item['profit_formatted']),
        profit_margin_percent: this.toNumber(item['profit_margin_percent']),
        profit: this.toNumber(item['profit']),
      })),
      type_data: this.mapArray(source['type_data'], (item) => ({
        type: this.toOptionalString(item['type']) ?? '',
        revenue: this.toNumber(item['revenue']),
      })),
      monthly_cashflow: this.mapArray(source['monthly_cashflow'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        total: this.toNumber(item['total']),
      })),
      payment_type_data: this.mapArray(source['payment_type_data'], (item) => ({
        type: this.toOptionalString(item['type']) ?? '',
        total: this.toNumber(item['total']),
      })),
      processing_time_data: this.mapArray(source['processing_time_data'], (item) => ({
        product: this.toOptionalString(item['product']) ?? '',
        avg_days: this.toNumber(item['avg_days']),
      })),
      total_by_month: this.mapArray(source['total_by_month'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        count: this.toNumber(item['count']),
      })),
      growth_rates: this.adaptGrowthRates(source['growth_rates']),
      yearly_data: this.mapArray(source['yearly_data'], (item) => ({
        year: this.toNumber(item['year']),
        total_cost: this.toNumber(item['total_cost']),
      })),
      monthly_data: this.mapArray(source['monthly_data'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        total_cost: this.toNumber(item['total_cost']),
        request_count: this.toNumber(item['request_count']),
      })),
      daily_data: this.mapArray(source['daily_data'], (item) => ({
        label: this.toOptionalString(item['label']) ?? '',
        total_cost: this.toNumber(item['total_cost']),
        request_count: this.toNumber(item['request_count']),
      })),
      feature_breakdown_month: this.mapArray(source['feature_breakdown_month'], (item) => ({
        feature: this.toOptionalString(item['feature']) ?? '',
        request_count: this.toNumber(item['request_count']),
        success_count: this.toNumber(item['success_count']),
        failed_count: this.toNumber(item['failed_count']),
        total_tokens: this.toNumber(item['total_tokens']),
        total_cost: this.toNumber(item['total_cost']),
      })),
      model_breakdown_month: this.mapArray(source['model_breakdown_month'], (item) => ({
        model: this.toOptionalString(item['model']) ?? '',
        request_count: this.toNumber(item['request_count']),
        success_count: this.toNumber(item['success_count']),
        failed_count: this.toNumber(item['failed_count']),
        total_tokens: this.toNumber(item['total_tokens']),
        total_cost: this.toNumber(item['total_cost']),
      })),
      invoices: this.mapArray(source['invoices'], (item) => ({
        invoice_number: this.toOptionalString(item['invoice_number']) ?? '',
        customer_name: this.toOptionalString(item['customer_name']) ?? '',
        invoice_date: this.toOptionalString(item['invoice_date']) ?? '',
        total_amount_formatted: this.toOptionalString(item['total_amount_formatted']),
        total_due_formatted: this.toOptionalString(item['total_due_formatted']),
      })),
      total_invoiced_formatted: this.toOptionalString(source['total_invoiced_formatted']),
      total_paid_formatted: this.toOptionalString(source['total_paid_formatted']),
      total_outstanding_formatted: this.toOptionalString(source['total_outstanding_formatted']),
      total_cashflow_formatted: this.toOptionalString(source['total_cashflow_formatted']),
      total_revenue_formatted: this.toOptionalString(source['total_revenue_formatted']),
      total_profit_formatted: this.toOptionalString(source['total_profit_formatted']),
      overall_profit_margin_percent: this.toOptionalNumber(source['overall_profit_margin_percent']),
      total_applications: this.toOptionalNumber(source['total_applications']),
    };

    return normalized;
  }

  private adaptPeriodSummary(value: unknown): ReportPeriodSummaryDto | undefined {
    const source = this.asNullableRecord(value);
    if (!source) {
      return undefined;
    }
    return {
      total_cost: this.toNumber(source['total_cost']),
      request_count: this.toNumber(source['request_count']),
    };
  }

  private adaptGrowthRates(value: unknown): Record<string, number> {
    const source = this.asNullableRecord(value);
    if (!source) {
      return {};
    }
    const result: Record<string, number> = {};
    Object.entries(source).forEach(([key, entryValue]) => {
      result[key] = this.toNumber(entryValue);
    });
    return result;
  }

  private normalizeToSnakeCase(value: unknown): unknown {
    if (Array.isArray(value)) {
      return value.map((item) => this.normalizeToSnakeCase(item));
    }

    const source = this.asNullableRecord(value);
    if (!source) {
      return value;
    }

    const normalized: Record<string, unknown> = {};
    Object.entries(source).forEach(([key, entryValue]) => {
      const snakeKey = key.replace(/([A-Z])/g, '_$1').toLowerCase();
      normalized[snakeKey] = this.normalizeToSnakeCase(entryValue);
    });
    return normalized;
  }

  private mapArray<T>(
    value: unknown,
    mapper: (entry: Record<string, unknown>) => T,
  ): T[] {
    if (!Array.isArray(value)) {
      return [];
    }
    return value.map((entry) => mapper(this.asRecord(entry)));
  }

  private asNullableRecord(value: unknown): Record<string, unknown> | null {
    if (!value || typeof value !== 'object' || Array.isArray(value)) {
      return null;
    }
    return value as Record<string, unknown>;
  }

  private asRecord(value: unknown): Record<string, unknown> {
    return this.asNullableRecord(value) ?? {};
  }

  private toOptionalString(value: unknown): string | undefined {
    if (typeof value !== 'string') {
      return undefined;
    }
    return value;
  }

  private toNumber(value: unknown): number {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : 0;
  }

  private toOptionalNumber(value: unknown): number | undefined {
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : undefined;
  }

  private toNullableNumber(value: unknown): number | null {
    if (value === null || value === undefined || value === '') {
      return null;
    }
    const parsed = Number(value);
    return Number.isFinite(parsed) ? parsed : null;
  }

  private toNumberArray(value: unknown): number[] {
    if (!Array.isArray(value)) {
      return [];
    }
    return value
      .map((entry) => Number(entry))
      .filter((entry) => Number.isFinite(entry));
  }
}
