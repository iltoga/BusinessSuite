import { ChangeDetectionStrategy, Component, computed, input } from '@angular/core';

import type { ClassValue } from 'clsx';

import { mergeClasses } from '@/shared/utils/merge-classes';

/**
 * Responsive grid container for `<app-detail-field>` items.
 *
 * - `cols="1"` (default) — items are stacked vertically with consistent spacing.
 * - `cols="2"` — two-column responsive grid (single column on mobile).
 *
 * Example:
 * ```html
 * <app-detail-grid>
 *   <app-detail-field layout="row" label="Type" value="Individual" />
 *   <app-detail-field layout="row" label="Email" value="foo@bar.com" />
 * </app-detail-grid>
 * ```
 */
@Component({
  selector: 'app-detail-grid',
  standalone: true,
  template: `
    <div [class]="classes()">
      <ng-content />
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class DetailGridComponent {
  readonly cols = input<1 | 2>(1);
  readonly class = input<ClassValue>('');

  protected readonly classes = computed(() => {
    const base =
      this.cols() === 2 ? 'grid grid-cols-1 md:grid-cols-2 gap-4' : 'flex flex-col gap-2.5';
    return mergeClasses(base, this.class());
  });
}
