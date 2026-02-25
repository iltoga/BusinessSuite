import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, OnInit, signal } from '@angular/core';
import { catchError, EMPTY, finalize } from 'rxjs';

import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';

interface OpenRouterStatusResponse {
  ok: boolean;
  openrouter: {
    configured: boolean;
    baseUrl: string;
    checkedAt: string;
    keyStatus: {
      ok: boolean;
      httpStatus: number | null;
      message: string | null;
      label: string | null;
      limit: number | null;
      limitRemaining: number | null;
      limitReset: string | null;
      usage: number | null;
      usageDaily: number | null;
      usageWeekly: number | null;
      usageMonthly: number | null;
      isFreeTier: boolean | null;
    };
    creditsStatus: {
      ok: boolean;
      available: boolean;
      httpStatus: number | null;
      message: string | null;
      totalCredits: number | null;
      totalUsage: number | null;
      remaining: number | null;
    };
    effectiveCreditRemaining: number | null;
    effectiveCreditSource: string | null;
  };
  aiModels: {
    provider: string;
    providerName: string;
    defaultModel: string;
    availableModels: Array<{ id: string; name: string; description?: string }>;
    usageCurrentMonth: {
      requestCount: number;
      successCount: number;
      failedCount: number;
      totalTokens: number;
      totalCost: number;
      year: number;
      month: number | null;
    };
    usageCurrentYear: {
      requestCount: number;
      successCount: number;
      failedCount: number;
      totalTokens: number;
      totalCost: number;
      year: number;
      month: number | null;
    };
    features: Array<{
      feature: string;
      purpose: string;
      modelStrategy: string;
      effectiveModel: string;
      provider: string;
      usageCurrentMonth: {
        requestCount: number;
        successCount: number;
        failedCount: number;
        totalTokens: number;
        totalCost: number;
        year: number;
        month: number | null;
      };
      usageCurrentYear: {
        requestCount: number;
        successCount: number;
        failedCount: number;
        totalTokens: number;
        totalCost: number;
        year: number;
        month: number | null;
      };
      modelBreakdownCurrentMonth: Array<{
        model: string;
        requestCount: number;
        successCount: number;
        failedCount: number;
        totalTokens: number;
        totalCost: number;
      }>;
      modelBreakdownCurrentYear: Array<{
        model: string;
        requestCount: number;
        successCount: number;
        failedCount: number;
        totalTokens: number;
        totalCost: number;
      }>;
    }>;
  };
}

@Component({
  selector: 'app-system-costs',
  standalone: true,
  imports: [CommonModule, ZardCardComponent, ZardButtonComponent, ZardBadgeComponent],
  templateUrl: './system-costs.component.html',
  styleUrls: ['./system-costs.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SystemCostsComponent implements OnInit {
  private readonly http = inject(HttpClient);
  private readonly toast = inject(GlobalToastService);

  readonly openRouterStatus = signal<OpenRouterStatusResponse | null>(null);
  readonly openRouterLoading = signal(false);

  ngOnInit(): void {
    this.loadOpenRouterStatus();
  }

  loadOpenRouterStatus(): void {
    this.openRouterLoading.set(true);
    this.http
      .get<OpenRouterStatusResponse>('/api/server-management/openrouter-status/')
      .pipe(
        catchError(() => {
          this.toast.error('Failed to load OpenRouter status');
          return EMPTY;
        }),
        finalize(() => this.openRouterLoading.set(false)),
      )
      .subscribe((response) => {
        this.openRouterStatus.set(response);
      });
  }

  getNonZeroCostModels<T extends { totalCost: number }>(models: T[] | null | undefined): T[] {
    if (!models?.length) {
      return [];
    }
    return models.filter((modelUsage) => Number(modelUsage.totalCost) > 0);
  }
}
