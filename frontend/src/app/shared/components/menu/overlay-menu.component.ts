import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, input, signal } from '@angular/core';

import { ZardIconComponent } from '@/shared/components/icon';
import { MenuItemComponent } from '@/shared/components/menu/menu-item.component';
import { MenuItem } from '@/shared/models/menu-item.model';

@Component({
  selector: 'app-overlay-menu',
  standalone: true,
  imports: [CommonModule, MenuItemComponent, ZardIconComponent],
  templateUrl: './overlay-menu.component.html',
  styleUrl: './overlay-menu.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class OverlayMenuComponent {
  readonly items = input.required<MenuItem[]>();
  readonly isMobileMenuOpen = signal(false);

  toggleMobileMenu(): void {
    this.isMobileMenuOpen.update((v) => !v);
  }

  onKeydown(event: KeyboardEvent): void {
    const menubar = event.currentTarget as HTMLElement;
    const menuItems = Array.from(
      menubar.querySelectorAll<HTMLElement>(':scope > ul > li [role="menuitem"]'),
    );
    const currentIndex = menuItems.indexOf(document.activeElement as HTMLElement);

    if (currentIndex < 0) return;

    if (event.key === 'ArrowRight') {
      event.preventDefault();
      menuItems[(currentIndex + 1) % menuItems.length]?.focus();
    }
    if (event.key === 'ArrowLeft') {
      event.preventDefault();
      menuItems[(currentIndex - 1 + menuItems.length) % menuItems.length]?.focus();
    }
    if (event.key === 'ArrowDown' || event.key === 'Enter') {
      event.preventDefault();
      (document.activeElement as HTMLElement)?.click();
    }
    if (event.key === 'Escape') {
      event.preventDefault();
      menuItems[0]?.focus();
    }
  }
}
