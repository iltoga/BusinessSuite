import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import type { ClassValue } from 'clsx';

import { ZardCardComponent } from '@/shared/components/card';

/**
 * Wrapper around `<z-card>` that enforces the compact card variant and provides
 * a standard title + optional actions header slot.
 *
 * Replaces the anti-pattern `<z-card class="p-4 sm:p-5">` or `<z-card class="p-4 sm:p-6">`
 * that manually fights ZardUI's built-in padding.
 *
 * Usage — card without title:
 * ```html
 * <app-card-section>
 *   <!-- content -->
 * </app-card-section>
 * ```
 *
 * Usage — card with title and action button:
 * ```html
 * <app-card-section title="Applications">
 *   <button card-section-actions z-button zType="outline" zSize="sm">New</button>
 *   <!-- content -->
 * </app-card-section>
 * ```
 *
 * The `[card-section-actions]` attribute marks elements projected into the header right side.
 * Extra classes (e.g. `mt-4`) can be passed via the `class` input.
 */
@Component({
  selector: 'app-card-section',
  standalone: true,
  imports: [ZardCardComponent],
  template: `
    <z-card zVariant="compact" [class]="class()">
      @if (title()) {
        <div class="flex flex-wrap items-center justify-between gap-3">
          <h2 class="text-lg font-semibold">{{ title() }}</h2>
          <ng-content select="[card-section-actions]" />
        </div>
      }
      <ng-content />
    </z-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class CardSectionComponent {
  readonly title = input<string>();
  readonly class = input<ClassValue>('');
}
