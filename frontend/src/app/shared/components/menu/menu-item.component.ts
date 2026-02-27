import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, HostBinding, inject, input } from '@angular/core';
import { RouterLink, RouterLinkActive } from '@angular/router';

import { ZardIconComponent } from '@/shared/components/icon';
import { MenuItem } from '@/shared/models/menu-item.model';
import { MenuService } from '@/shared/services/menu.service';

@Component({
  selector: 'app-menu-item',
  standalone: true,
  imports: [CommonModule, RouterLink, RouterLinkActive, ZardIconComponent],
  templateUrl: './menu-item.component.html',
  styleUrl: './menu-item.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MenuItemComponent {
  readonly item = input.required<MenuItem>();
  readonly depth = input(0);
  readonly mode = input<'sidebar' | 'overlay'>('sidebar');

  readonly menuService = inject(MenuService);

  @HostBinding('attr.role')
  role = 'none';

  @HostBinding('attr.app-region')
  get appRegion(): 'no-drag' | null {
    return this.mode() === 'overlay' ? 'no-drag' : null;
  }

  isExpanded(): boolean {
    return !this.menuService.isCollapsed(this.item().id);
  }

  toggleExpanded(event: Event): void {
    event.preventDefault();
    event.stopPropagation();

    if (this.mode() === 'overlay' && this.depth() === 0) {
      this.menuService.toggleOverlayRootCollapse(this.item().id);
      return;
    }

    this.menuService.toggleCollapse(this.item().id);
  }

  runAction(): void {
    this.item().action?.();
  }
}
