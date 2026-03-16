import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Renders the standard uppercase section-heading used on detail pages.
 *
 * Replaces the repeated inline pattern:
 * `<h3 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">…</h3>`
 */
@Component({
  selector: 'app-section-header',
  standalone: true,
  template: `
    <h3 class="text-sm font-semibold text-muted-foreground uppercase tracking-wide mb-3">
      {{ text() }}
    </h3>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class SectionHeaderComponent {
  readonly text = input.required<string>();
}
