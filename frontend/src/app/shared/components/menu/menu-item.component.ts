import {
  ChangeDetectionStrategy,
  Component,
  HostBinding,
  computed,
  inject,
  input,
  OnDestroy,
} from '@angular/core';
import { toSignal } from '@angular/core/rxjs-interop';
import { NavigationEnd, Router, RouterLink } from '@angular/router';
import { filter, map, startWith } from 'rxjs';

import { ZardIconComponent } from '@/shared/components/icon';
import { MenuItem } from '@/shared/models/menu-item.model';
import { MenuService } from '@/shared/services/menu.service';

@Component({
  selector: 'app-menu-item',
  standalone: true,
  imports: [RouterLink, ZardIconComponent],
  templateUrl: './menu-item.component.html',
  styleUrl: './menu-item.component.css',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class MenuItemComponent implements OnDestroy {
  readonly item = input.required<MenuItem>();
  readonly depth = input(0);
  readonly mode = input<'sidebar' | 'overlay'>('sidebar');

  readonly menuService = inject(MenuService);
  private readonly router = inject(Router);

  private collapseTimer: ReturnType<typeof setTimeout> | null = null;
  private readonly currentUrl = toSignal(
    this.router.events.pipe(
      filter((event): event is NavigationEnd => event instanceof NavigationEnd),
      map(() => this.router.url),
      startWith(this.router.url),
    ),
    { initialValue: this.router.url },
  );
  readonly isActive = computed(() => {
    const menuItem = this.item();
    const route = menuItem.route;
    if (!route) {
      return false;
    }

    // Track router state reactively so active menu styling updates after imperative navigation.
    this.currentUrl();

    return this.router.isActive(route, {
      paths: menuItem.children?.length ? 'subset' : 'exact',
      queryParams: 'ignored',
      fragment: 'ignored',
      matrixParams: 'ignored',
    });
  });

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

  onOverlayMouseEnter(): void {
    if (this.collapseTimer) {
      clearTimeout(this.collapseTimer);
      this.collapseTimer = null;
    }
  }

  onOverlayMouseLeave(): void {
    if (this.mode() !== 'overlay') return;
    this.collapseTimer = setTimeout(() => {
      this.menuService.collapseOverlayRootMenus();
      this.collapseTimer = null;
    }, 150);
  }

  runAction(): void {
    this.item().action?.();
  }

  ngOnDestroy(): void {
    if (this.collapseTimer) {
      clearTimeout(this.collapseTimer);
    }
  }
}
