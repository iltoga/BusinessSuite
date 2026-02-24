import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  computed,
  effect,
  input,
  output,
  signal,
} from '@angular/core';

import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';

export interface CategorizationFileResult {
  itemId: string;
  filename: string;
  status: 'queued' | 'processing' | 'categorized' | 'error';
  documentType: string | null;
  documentTypeId: number | null;
  documentId: number | null;
  confidence: number;
  reasoning: string;
  error: string | null;
  categorizationPass: number | null;
  validationStatus: 'valid' | 'invalid' | 'pending' | null;
  validationReasoning: string | null;
  validationNegativeIssues: string[] | null;
}

export interface CategorizationApplyMapping {
  itemId: string;
  documentId: number;
}

@Component({
  selector: 'app-categorization-progress',
  standalone: true,
  imports: [CommonModule, ZardBadgeComponent, ZardButtonComponent],
  templateUrl: './categorization-progress.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CategorizationProgressComponent {
  readonly totalFiles = input.required<number>();
  readonly processedFiles = input<number>(0);
  readonly results = input<CategorizationFileResult[]>([]);
  readonly isComplete = input<boolean>(false);
  readonly isApplying = input<boolean>(false);
  readonly statusMessage = input<string>('');

  readonly applyAll = output<CategorizationApplyMapping[]>();
  readonly dismiss = output<void>();
  readonly dismissSelected = output<string[]>();
  readonly selectedResultKeys = signal<Set<string>>(new Set());

  readonly progressPercent = computed(() => {
    const total = this.totalFiles();
    if (total === 0) return 0;
    return Math.round((this.processedFiles() / total) * 100);
  });

  readonly categorizedResults = computed(() =>
    this.results().filter((r) => r.status === 'categorized' && r.documentId),
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

  readonly validatingResults = computed(() =>
    this.results().filter((r) => r.validationStatus === 'pending'),
  );

  readonly canApply = computed(
    () => this.isComplete() && this.categorizedResults().length > 0 && !this.isApplying(),
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
    const mappings = this.categorizedResults().map((r) => ({
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
}
