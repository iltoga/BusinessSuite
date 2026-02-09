import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component } from '@angular/core';

interface HotkeySection {
  title: string;
  items: string[];
}

@Component({
  selector: 'z-hotkeys-drawer-content',
  standalone: true,
  imports: [CommonModule],
  template: `
    <div class="p-4">
      <div class="flex items-start justify-between">
        <div>
          <h2 class="text-lg font-semibold">Keyboard Shortcuts</h2>
          <p class="text-sm text-muted-foreground mt-1">
            Cheatsheet of common shortcuts across the app.
          </p>
        </div>
        <div>
          <!-- The close button is provided by the sheet footer/hide controls; keep header minimal -->
        </div>
      </div>

      <div class="mt-4 space-y-4">
        <ng-container *ngFor="let s of sections">
          <div>
            <h3 class="text-sm font-medium text-slate-700">{{ s.title }}</h3>
            <ul class="text-sm text-slate-600 mt-2 space-y-1">
              <li *ngFor="let i of s.items">{{ i }}</li>
            </ul>
          </div>
        </ng-container>
      </div>

      <div class="mt-6 text-xs text-muted-foreground">
        Tip: Press <strong>Shift+K</strong> to open this cheatsheet at any time.
      </div>
    </div>
  `,
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class HotkeysDrawerContentComponent {
  sections: HotkeySection[] = [
    {
      title: 'General',
      items: [
        'F1: Open contextual help (current view)',
        'Shift+K: Open this shortcuts cheatsheet',
        'Shift+S: Focus search (any view)',
        'Shift+T: Focus table (list views)',
      ],
    },
    {
      title: 'Side menu',
      items: [
        'Shift+M: Open and focus main menu',
        'Shift+D: Open Dashboard',
        'Shift+C: Open Customers',
        'Shift+A: Open Applications',
        'Shift+P: Open Products',
        'Shift+I: Open Invoices',
        'Shift+L: Open letters section and focus sub-item',
      ],
    },
    {
      title: 'Tables',
      items: ['ArrowUp / ArrowDown: Navigate rows', 'Space: Open row actions menu'],
    },
    {
      title: 'Search & Filters',
      items: ['s: Focus search toolbar (Shift+S also works)', 'Enter: Submit search'],
    },
    {
      title: 'Navigation',
      items: ['Shift+T: Focus table view', 'Shift+N: Create new entity (in list views)'],
    },
  ];
}
