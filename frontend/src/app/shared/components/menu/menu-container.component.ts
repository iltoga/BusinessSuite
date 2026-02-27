import { BreakpointObserver } from '@angular/cdk/layout';
import { CommonModule } from '@angular/common';
import { ChangeDetectionStrategy, Component, computed, inject } from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { map } from 'rxjs';

import { ConfigService } from '@/core/services/config.service';
import { OverlayMenuComponent } from '@/shared/components/menu/overlay-menu.component';
import { SidebarMenuComponent } from '@/shared/components/menu/sidebar-menu.component';
import { MenuService } from '@/shared/services/menu.service';
import { PwaOverlayService } from '@/shared/services/pwa-overlay.service';

@Component({
  selector: 'app-menu-container',
  standalone: true,
  imports: [CommonModule, SidebarMenuComponent, OverlayMenuComponent],
  templateUrl: './menu-container.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MenuContainerComponent {
  private readonly menuService = inject(MenuService);
  private readonly overlayService = inject(PwaOverlayService);
  private readonly configService = inject(ConfigService);
  private readonly breakpointObserver = inject(BreakpointObserver);

  readonly isOverlayDesktopViewport = toSignal(
    this.breakpointObserver.observe('(min-width: 768px)').pipe(map((state) => state.matches)),
    { initialValue: true },
  );
  readonly isOverlayMode = toSignal(this.overlayService.isOverlayMode$, { initialValue: false });
  readonly useOverlayMenu = computed(
    () =>
      this.isOverlayDesktopViewport() &&
      (this.isOverlayMode() || Boolean(this.configService.config().useOverlayMenu)),
  );
  readonly menuItems = this.menuService.visibleMenuItems;
  readonly showSidebar = computed(() => !this.useOverlayMenu());
}
