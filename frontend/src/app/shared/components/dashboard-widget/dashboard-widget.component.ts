import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-dashboard-widget',
  standalone: true,
  imports: [CommonModule, ZardCardComponent],
  template: `
    <z-card class="p-4 h-full bg-card/80 backdrop-blur border-border/60">
      <div class="flex items-center justify-between mb-3">
        <h3 class="font-semibold text-base">{{ widgetTitle() }}</h3>
        <span class="text-xs text-muted-foreground">{{ widgetSubtitle() }}</span>
      </div>
      <ng-content />
    </z-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardWidgetComponent {
  readonly widgetTitle = input.required<string>();
  readonly widgetSubtitle = input<string>('');
}
