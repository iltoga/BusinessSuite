import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, input } from '@angular/core';

import { MenuItemComponent } from '@/shared/components/menu/menu-item.component';
import { MenuItem } from '@/shared/models/menu-item.model';

@Component({
  selector: 'app-sidebar-menu',
  standalone: true,
  imports: [CommonModule, MenuItemComponent],
  templateUrl: './sidebar-menu.component.html',
  styleUrl: './sidebar-menu.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class SidebarMenuComponent {
  readonly items = input.required<MenuItem[]>();

  onKeydown(event: KeyboardEvent): void {
    const container = event.currentTarget as HTMLElement;
    const menuItems = Array.from(container.querySelectorAll<HTMLElement>('[role="menuitem"]'));
    const currentIndex = menuItems.indexOf(document.activeElement as HTMLElement);

    if (currentIndex < 0 || !['ArrowDown', 'ArrowUp', 'Enter', 'Escape'].includes(event.key)) return;

    if (event.key === 'ArrowDown') {
      event.preventDefault();
      menuItems[(currentIndex + 1) % menuItems.length]?.focus();
    }
    if (event.key === 'ArrowUp') {
      event.preventDefault();
      menuItems[(currentIndex - 1 + menuItems.length) % menuItems.length]?.focus();
    }
    if (event.key === 'Enter') {
      event.preventDefault();
      menuItems[currentIndex]?.click();
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      menuItems[0]?.focus();
    }
  }
}
