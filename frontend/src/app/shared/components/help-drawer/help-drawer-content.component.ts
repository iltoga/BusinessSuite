import { ZardButtonComponent } from '@/shared/components/button/button.component';
import { ZardIconComponent } from '@/shared/components/icon/icon.component';
import { HelpService } from '@/shared/services/help.service';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, inject } from '@angular/core';

@Component({
  selector: 'z-help-drawer-content',
  standalone: true,
  imports: [CommonModule, ZardButtonComponent, ZardIconComponent],
  template: `
    <div class="p-4">
      <div class="flex items-start justify-between">
        <div>
          <h2 class="text-lg font-semibold">Help</h2>
          <p class="text-xs text-muted-foreground mt-2">Opened {{ help.openCount() }} times</p>
        </div>
        <div>
          <button type="button" z-button zType="ghost" zSize="sm" (click)="help.close()">
            <z-icon zType="x"></z-icon>
          </button>
        </div>
      </div>

      <div class="mt-4 space-y-4">
        <div *ngIf="context()?.briefExplanation">
          <h3 class="text-sm font-medium text-slate-700">Brief Explanation</h3>
          <p class="text-sm text-slate-600 mt-1">{{ context()?.briefExplanation }}</p>
        </div>

        <div *ngIf="context()?.details">
          <h3 class="text-sm font-medium text-slate-700">Details</h3>
          <p class="text-sm text-slate-600 mt-1">{{ context()?.details }}</p>
        </div>

        <div *ngIf="!context()?.briefExplanation && !context()?.details">
          <p class="text-sm text-slate-600">
            More detailed help will appear here for the current view.
          </p>
        </div>
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HelpDrawerContentComponent {
  readonly help = inject(HelpService);
  readonly context = this.help.context;
}
