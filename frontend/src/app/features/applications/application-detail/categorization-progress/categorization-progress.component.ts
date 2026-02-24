import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input, output } from '@angular/core';

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

  readonly canApply = computed(
    () => this.isComplete() && this.categorizedResults().length > 0 && !this.isApplying(),
  );

  readonly applyLabel = computed(() => {
    const count = this.categorizedResults().length;
    return count > 0 ? `Apply ${count} Matched File(s)` : 'No Matches to Apply';
  });

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
