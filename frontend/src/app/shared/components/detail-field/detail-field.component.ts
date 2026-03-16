import { ChangeDetectionStrategy, Component, input } from '@angular/core';

/**
 * Renders a single label + value row used on detail pages.
 *
 * **Simple string value:**
 * ```html
 * <app-detail-field label="Status" value="Active" />
 * ```
 *
 * **Complex projected value** (badges, links, etc.) — omit `value` and project content:
 * ```html
 * <app-detail-field label="Status">
 *   <z-badge zType="success">Active</z-badge>
 * </app-detail-field>
 * ```
 *
 * When `value` is bound (even to `null` or `''`), the string is rendered with a `—` fallback.
 * When `value` is NOT bound (`undefined`), the projected `ng-content` is rendered instead.
 *
 * Layouts:
 * - `col` (default) — label on top, value below; suits address/notes fields.
 * - `row` — label and value side-by-side in a 2-column grid; suits key/value lists.
 */
@Component({
  selector: 'app-detail-field',
  standalone: true,
  template: `
    @if (layout() === 'row') {
      <div class="grid grid-cols-[minmax(0,1fr)_minmax(0,1.2fr)] gap-2 items-start">
        <span class="text-sm text-muted-foreground">{{ label() }}</span>
        <span class="text-sm font-medium">
          @if (value() !== undefined) {
            {{ value() || '—' }}
          } @else {
            <ng-content />
          }
        </span>
      </div>
    } @else {
      <div>
        <div class="text-sm text-muted-foreground">{{ label() }}</div>
        <div class="text-sm font-medium">
          @if (value() !== undefined) {
            {{ value() || '—' }}
          } @else {
            <ng-content />
          }
        </div>
      </div>
    }
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
  host: { class: 'block' },
})
export class DetailFieldComponent {
  readonly label = input.required<string>();
  readonly value = input<string | null | undefined>();
  readonly layout = input<'row' | 'col'>('col');
}
