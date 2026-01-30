import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { ZardSkeletonComponent } from './skeleton.component';

import { ZardCardComponent } from '@/shared/components/card';

@Component({
  selector: 'app-card-skeleton',
  standalone: true,
  imports: [CommonModule, ZardCardComponent, ZardSkeletonComponent],
  template: `
    <z-card class="p-6">
      <div class="space-y-4">
        @if (showHeader()) {
          <z-skeleton class="h-6 w-1/3" />
        }
        <div class="space-y-2">
          @for (i of [].constructor(lines()); track $index) {
            <z-skeleton class="h-4 w-full" />
          }
        </div>
      </div>
    </z-card>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class CardSkeletonComponent {
  showHeader = input<boolean>(true);
  lines = input<number>(3);
}
