import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  isDevMode,
  input,
  output,
  PLATFORM_ID,
  signal,
  inject,
} from '@angular/core';

import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardIconComponent } from '@/shared/components/icon';
import { ZardTableComponent } from '@/shared/components/table';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  getCategorizationResultStatusBadge,
  getCategorizationValidationBadge,
  isCategorizationPipelineTerminal,
  type PipelineBadgeState,
  type CategorizationValidationStatus,
} from '@/core/utils/document-categorization-pipeline';

export interface CategorizationFileResult {
  itemId: string;
  filename: string;
  status: 'uploading' | 'queued' | 'processing' | 'categorized' | 'error';
  pipelineStage:
    | 'uploading'
    | 'uploaded'
    | 'categorizing'
    | 'categorized'
    | 'validating'
    | 'validated'
    | 'error';
  aiValidationEnabled: boolean | null;
  documentType: string | null;
  documentTypeId: number | null;
  documentId: number | null;
  confidence: number;
  reasoning: string;
  error: string | null;
  categorizationPass: number | null;
  validationStatus: CategorizationValidationStatus;
  validationReasoning: string | null;
  validationNegativeIssues: string[] | null;
  validationProvider?: string | null;
  validationProviderName?: string | null;
  validationModel?: string | null;
}

export interface CategorizationApplyMapping {
  itemId: string;
  documentId: number;
}

@Component({
  selector: 'app-categorization-progress',
  standalone: true,
  imports: [
    CommonModule,
    ZardBadgeComponent,
    ZardButtonComponent,
    ZardCardComponent,
    ZardIconComponent,
    ZardTableComponent,
    ...ZardTooltipImports,
  ],
  templateUrl: './categorization-progress.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CategorizationProgressComponent {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly toast = inject(GlobalToastService);

  readonly isDevelopmentMode = isDevMode();
  readonly isBrowser = this.platformId === 'browser';
  readonly totalFiles = input.required<number>();
  readonly processedFiles = input<number>(0);
  readonly progressPercentOverride = input<number | null>(null);
  readonly results = input<CategorizationFileResult[]>([]);
  readonly isComplete = input<boolean>(false);
  readonly isApplying = input<boolean>(false);
  readonly statusMessage = input<string>('');

  readonly applyAll = output<CategorizationApplyMapping[]>();
  readonly dismiss = output<void>();
  readonly dismissSelected = output<string[]>();
  readonly selectedResultKeys = signal<Set<string>>(new Set());

  readonly progressPercent = computed(() => {
    const override = this.progressPercentOverride();
    if (typeof override === 'number' && Number.isFinite(override)) {
      return Math.max(0, Math.min(100, Math.round(override)));
    }

    const total = this.totalFiles();
    if (total === 0) return 0;
    return Math.round((this.processedFiles() / total) * 100);
  });

  readonly categorizedResults = computed(() =>
    this.results().filter((r) => r.status === 'categorized' && r.documentId && r.itemId),
  );

  readonly unmatchedResults = computed(() =>
    this.results().filter((r) => r.status === 'categorized' && !r.documentId),
  );

  readonly errorResults = computed(() => this.results().filter((r) => r.status === 'error'));

  readonly validResults = computed(() =>
    this.results().filter((r) => r.validationStatus === 'valid'),
  );

  readonly invalidResults = computed(() =>
    this.results().filter((r) => r.validationStatus === 'invalid'),
  );
  readonly validationErrorResults = computed(() =>
    this.results().filter((r) => r.validationStatus === 'error'),
  );
  readonly hasUnresolvedResults = computed(() => {
    const total = this.totalFiles();
    const results = this.results();
    if (total <= 0 || results.length < total) {
      return true;
    }
    return results.some((result) => !isCategorizationPipelineTerminal(result));
  });

  readonly canApply = computed(
    () =>
      this.isComplete() &&
      !this.hasUnresolvedResults() &&
      this.categorizedResults().length > 0 &&
      !this.isApplying(),
  );

  readonly applyLabel = computed(() => {
    const count = this.categorizedResults().length;
    return count > 0 ? `Apply ${count} Matched File(s)` : 'No Matches to Apply';
  });
  readonly selectableResultKeys = computed(() =>
    this.results().map((result, index) => this.getResultKey(result, index)),
  );
  readonly selectedCount = computed(() => this.selectedResultKeys().size);
  readonly allSelected = computed(() => {
    const keys = this.selectableResultKeys();
    if (keys.length === 0) {
      return false;
    }
    const selected = this.selectedResultKeys();
    return keys.every((key) => selected.has(key));
  });
  readonly selectionPartial = computed(() => {
    const total = this.selectableResultKeys().length;
    if (total === 0) {
      return false;
    }
    const selected = this.selectedResultKeys().size;
    return selected > 0 && selected < total;
  });
  readonly canDismissSelected = computed(
    () => this.isComplete() && this.selectedCount() > 0 && !this.isApplying(),
  );

  constructor() {
    effect(() => {
      const availableKeys = new Set(this.selectableResultKeys());
      this.selectedResultKeys.update((current) => {
        if (current.size === 0) {
          return current;
        }
        const filtered = new Set([...current].filter((key) => availableKeys.has(key)));
        if (filtered.size === current.size) {
          return current;
        }
        return filtered;
      });
    });
  }

  getResultKey(result: CategorizationFileResult, index: number): string {
    return result.itemId || `${result.filename}-${index}`;
  }

  isResultSelected(result: CategorizationFileResult, index: number): boolean {
    return this.selectedResultKeys().has(this.getResultKey(result, index));
  }

  toggleResultSelection(result: CategorizationFileResult, index: number, checked: boolean): void {
    const key = this.getResultKey(result, index);
    this.selectedResultKeys.update((current) => {
      const next = new Set(current);
      if (checked) {
        next.add(key);
      } else {
        next.delete(key);
      }
      return next;
    });
  }

  toggleAllSelection(checked: boolean): void {
    if (!checked) {
      this.selectedResultKeys.set(new Set());
      return;
    }
    this.selectedResultKeys.set(new Set(this.selectableResultKeys()));
  }

  onApplyAll(): void {
    const mappings = this.categorizedResults()
      .filter((result) => result.itemId.trim().length > 0)
      .map((r) => ({
        itemId: r.itemId,
        documentId: r.documentId!,
      }));
    if (mappings.length > 0) {
      this.applyAll.emit(mappings);
    }
  }

  onDismiss(): void {
    this.dismiss.emit();
  }

  onDismissSelected(): void {
    const selected = [...this.selectedResultKeys()];
    if (selected.length === 0) {
      return;
    }
    this.dismissSelected.emit(selected);
    this.selectedResultKeys.set(new Set());
  }

  getConfidenceBadgeType(confidence: number): string {
    if (confidence >= 0.8) return 'success';
    if (confidence >= 0.5) return 'warning';
    return 'destructive';
  }

  formatConfidence(confidence: number): string {
    return `${Math.round(confidence * 100)}%`;
  }

  getStatusIcon(status: string): string {
    switch (status) {
      case 'uploading':
        return '📤';
      case 'queued':
        return '⏳';
      case 'processing':
        return '🔄';
      case 'categorized':
        return '✅';
      case 'error':
        return '❌';
      default:
        return '●';
    }
  }

  getResultStatusBadge(result: CategorizationFileResult): PipelineBadgeState {
    return getCategorizationResultStatusBadge(result);
  }

  getValidationBadge(result: CategorizationFileResult): PipelineBadgeState | null {
    return getCategorizationValidationBadge(result);
  }

  getPipelineTrack(result: CategorizationFileResult): string {
    const upload = result.pipelineStage === 'uploading' ? 'Upload ⏳' : 'Upload ✓';

    let categorize = 'Categorize …';
    if (result.pipelineStage === 'categorizing' || result.status === 'processing') {
      categorize = 'Categorize ⏳';
    } else if (
      result.pipelineStage === 'categorized' ||
      result.pipelineStage === 'validating' ||
      result.pipelineStage === 'validated'
    ) {
      categorize = 'Categorize ✓';
    } else if (result.pipelineStage === 'error' && !result.documentType) {
      categorize = 'Categorize ✗';
    }

    let validate = 'Validate …';
    if (result.aiValidationEnabled === false) {
      validate = 'Validate skipped';
    } else if (result.pipelineStage === 'validating' || result.validationStatus === 'pending') {
      validate = 'Validate ⏳';
    } else if (result.validationStatus === 'valid') {
      validate = 'Validate ✓';
    } else if (result.validationStatus === 'invalid' || result.validationStatus === 'error') {
      validate = 'Validate ✗';
    }

    return `${upload} → ${categorize} → ${validate}`;
  }

  getValidationTooltip(result: CategorizationFileResult): string {
    const reasoning = (result.validationReasoning ?? '').trim();
    if (!this.isDevelopmentMode) {
      return reasoning;
    }

    const runtime = this.formatAiRuntimeLabel(
      result.validationProviderName ?? null,
      result.validationProvider ?? null,
      result.validationModel ?? null,
    );
    if (!runtime) {
      return reasoning;
    }

    return reasoning ? `${reasoning} | AI runtime: ${runtime}` : `AI runtime: ${runtime}`;
  }

  async copyValidationTooltip(result: CategorizationFileResult): Promise<void> {
    const payload = this.getValidationTooltip(result).trim();
    if (!payload) {
      this.toast.error('Nothing to copy');
      return;
    }

    const copied = await this.copyToClipboard(payload);
    if (copied) {
      this.toast.success('Validation details copied');
      return;
    }

    this.toast.error('Could not copy validation details');
  }

  private async copyToClipboard(text: string): Promise<boolean> {
    if (!this.isBrowser || !text) {
      return false;
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // Fallback below for browsers or shells without navigator.clipboard support.
    }

    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '-1000px';
      textarea.style.left = '-1000px';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const copied = document.execCommand('copy');
      document.body.removeChild(textarea);
      return copied;
    } catch {
      return false;
    }
  }

  private formatAiRuntimeLabel(
    providerName: string | null,
    provider: string | null,
    model: string | null,
  ): string {
    const providerLabel = (providerName ?? provider ?? '').trim();
    const modelLabel = (model ?? '').trim();

    if (providerLabel && modelLabel) {
      return `${providerLabel} / ${modelLabel}`;
    }
    return providerLabel || modelLabel;
  }
}
