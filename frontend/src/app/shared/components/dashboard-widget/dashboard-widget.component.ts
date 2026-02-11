import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';
import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-dashboard-widget',
  standalone: true,
  imports: [CommonModule, ZardCardComponent],
  template: `
    <z-card class="p-4 h-full">
      <div class="flex items-center justify-between mb-3">
        <h3 class="text-base font-semibold">{{ title() }}</h3>
        <ng-content select="[widgetActions]"></ng-content>
      </div>
      <div class="text-sm text-muted-foreground mb-3" *ngIf="subtitle()">{{ subtitle() }}</div>
      <ng-content></ng-content>
    </z-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class DashboardWidgetComponent {
  readonly title = input.required<string>();
  readonly subtitle = input<string>('');
}
