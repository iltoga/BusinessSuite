import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';
import type { AbstractControl } from '@angular/forms';

import { collectServerErrors } from '@/shared/utils/form-errors';

@Component({
  selector: 'app-form-error-summary',
  standalone: true,
  imports: [CommonModule],
  template: `
    @if (errors().length > 0) {
      <div
        class="rounded-md border border-destructive/40 bg-destructive/10 p-3 text-sm text-destructive"
      >
        <div class="font-medium mb-1">Please fix the highlighted fields:</div>
        <ul class="list-disc pl-5 space-y-1">
          @for (err of errors(); track err.path) {
            <li>{{ err.label }}: {{ err.message }}</li>
          }
        </ul>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class FormErrorSummaryComponent {
  readonly form = input<AbstractControl | null>(null);
  readonly labels = input<Record<string, string>>({});

  readonly errors = computed(() => {
    const control = this.form();
    if (!control) return [];
    return collectServerErrors(control, this.labels());
  });
}
