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
        <h3 class="font-semibold text-base">{{ title() }}</h3>
        <span class="text-xs text-muted-foreground">{{ subtitle() }}</span>
      </div>
      <ng-content />
    </z-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardWidgetComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>('');
}
