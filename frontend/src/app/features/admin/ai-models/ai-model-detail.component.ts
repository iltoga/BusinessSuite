import { ChangeDetectionStrategy, Component, computed, inject, type OnInit } from '@angular/core';
import { Observable } from 'rxjs';

import { AiModelsService } from '@/core/api/api/ai-models.service';
import type { AiModel } from '@/core/api/model/ai-model';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { CardSectionComponent } from '@/shared/components/card-section';
import { DetailFieldComponent } from '@/shared/components/detail-field';
import { DetailGridComponent } from '@/shared/components/detail-grid';
import { SectionHeaderComponent } from '@/shared/components/section-header';
import { CardSkeletonComponent, ZardSkeletonComponent } from '@/shared/components/skeleton';
import { BaseDetailComponent, BaseDetailConfig } from '@/shared/core/base-detail.component';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

@Component({
  selector: 'app-ai-model-detail',
  standalone: true,
  imports: [
    ZardBadgeComponent,
    ZardButtonComponent,
    CardSectionComponent,
    DetailFieldComponent,
    DetailGridComponent,
    CardSkeletonComponent,
    ZardSkeletonComponent,
    SectionHeaderComponent,
    AppDatePipe,
  ],
  templateUrl: './ai-model-detail.component.html',
  styleUrls: ['./ai-model-detail.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class AiModelDetailComponent extends BaseDetailComponent<AiModel> implements OnInit {
  private readonly aiModelsApi = inject(AiModelsService);

  readonly providerLabel = computed(() => this.humanizeProvider(this.item()?.provider));
  readonly sourceLabel = computed(() => this.humanizeLabel(this.item()?.source));
  readonly topProviderLabel = computed(() => this.formatOptionalText(this.item()?.topProviderId));
  readonly modalityText = computed(() => this.formatOptionalText(this.item()?.modality));
  readonly architectureModalityText = computed(() =>
    this.formatOptionalText(this.item()?.architectureModality),
  );
  readonly tokenizerText = computed(() =>
    this.formatOptionalText(this.item()?.architectureTokenizer),
  );
  readonly instructTypeText = computed(() => this.formatOptionalText(this.item()?.instructType));
  readonly supportedParameters = computed(() =>
    this.normalizedStringList(this.item()?.supportedParameters),
  );
  readonly perRequestLimitsText = computed(() => this.prettyJson(this.item()?.perRequestLimits));
  readonly rawMetadataText = computed(() => this.prettyJson(this.item()?.rawMetadata));
  readonly contextLengthText = computed(() =>
    this.formatOptionalNumber(this.item()?.contextLength),
  );
  readonly maxCompletionTokensText = computed(() =>
    this.formatOptionalNumber(this.item()?.maxCompletionTokens),
  );

  readonly pricingRows = computed(() => {
    const item = this.item();
    if (!item) {
      return [] as Array<{ label: string; value: string }>;
    }

    return [
      {
        label: 'Prompt Price (per 1M tokens)',
        value: this.formatDisplayPrice(item.pricingDisplay?.promptPricePerMillionTokens),
      },
      {
        label: 'Completion Price (per 1M tokens)',
        value: this.formatDisplayPrice(item.pricingDisplay?.completionPricePerMillionTokens),
      },
      {
        label: 'Image Price (per 1M tokens)',
        value: this.formatDisplayPrice(item.pricingDisplay?.imagePricePerMillionTokens),
      },
      {
        label: 'Request Price (per 1M tokens)',
        value: this.formatDisplayPrice(item.pricingDisplay?.requestPricePerMillionTokens),
      },
    ];
  });

  constructor() {
    super();
    this.config = {
      entityType: 'admin/ai-models',
      entityLabel: 'AI Model',
      enableDelete: true,
      messages: {
        loadError: 'Failed to load AI model',
        deleteConfirm: (item) =>
          `Delete AI model ${item.name || item.modelId || `#${item.id}`}? This cannot be undone.`,
        deleteSuccess: 'AI model deleted successfully',
        deleteError: 'Failed to delete AI model',
      },
    } as BaseDetailConfig<AiModel>;
  }

  protected override loadItem(id: number): Observable<AiModel> {
    return this.aiModelsApi.aiModelsRetrieve({ id });
  }

  override ngOnInit(): void {
    super.ngOnInit();
  }

  onEdit(): void {
    const item = this.item();
    if (!item) {
      return;
    }

    this.router.navigate(['/admin/ai-models', item.id, 'edit'], {
      state: {
        from: 'admin-ai-models',
        focusId: item.id,
        searchQuery: this.originSearchQuery(),
        page: this.originPage() ?? undefined,
      },
    });
  }

  deleteModel(): void {
    this.onDelete();
  }

  protected override deleteItem(id: number): Observable<any> {
    return this.aiModelsApi.aiModelsDestroy({ id });
  }

  badgeType(value?: boolean): 'success' | 'secondary' {
    return value ? 'success' : 'secondary';
  }

  yesNo(value?: boolean): string {
    return value ? 'Yes' : 'No';
  }

  private formatDisplayPrice(value: string | number | null | undefined): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }

    const numericPrice = Number(value);
    if (!Number.isFinite(numericPrice)) {
      return '—';
    }

    return numericPrice.toFixed(2);
  }

  private formatOptionalNumber(value: number | null | undefined): string {
    if (value === null || value === undefined || !Number.isFinite(value)) {
      return '—';
    }

    return value.toString();
  }

  private humanizeProvider(value?: string | null): string {
    if (!value) {
      return '—';
    }

    const normalized = value.toLowerCase();
    switch (normalized) {
      case 'openrouter':
        return 'OpenRouter';
      case 'openai':
        return 'OpenAI';
      case 'groq':
        return 'Groq';
      default:
        return this.humanizeLabel(value);
    }
  }

  private formatOptionalText(value?: string | null): string {
    if (!value) {
      return '—';
    }

    const trimmed = value.trim();
    return trimmed.length > 0 ? trimmed : '—';
  }

  private humanizeLabel(value?: string | null): string {
    if (!value) {
      return '—';
    }

    return value
      .toString()
      .replace(/[_-]+/g, ' ')
      .replace(/\s+/g, ' ')
      .trim()
      .replace(/\b\w/g, (match) => match.toUpperCase());
  }

  private normalizedStringList(value: unknown): string[] {
    if (!Array.isArray(value)) {
      return [];
    }

    return value
      .map((entry) => (typeof entry === 'string' ? entry.trim() : ''))
      .filter((entry) => entry.length > 0);
  }

  private prettyJson(value: unknown): string {
    if (value === null || value === undefined || value === '') {
      return '—';
    }

    if (typeof value === 'string') {
      const trimmed = value.trim();
      if (!trimmed) {
        return '—';
      }

      try {
        const parsed = JSON.parse(trimmed) as unknown;
        return JSON.stringify(parsed, null, 2);
      } catch {
        return trimmed;
      }
    }

    try {
      return JSON.stringify(value, null, 2);
    } catch {
      return String(value);
    }
  }
}
