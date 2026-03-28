import { TestBed } from '@angular/core/testing';
import { provideRouter, Router } from '@angular/router';

import { MenuService } from '@/shared/services/menu.service';

import { MenuItemComponent } from './menu-item.component';

describe('MenuItemComponent', () => {
  let router: Router;
  let component: MenuItemComponent;

  beforeEach(() => {
    TestBed.configureTestingModule({
      providers: [
        provideRouter([
          { path: 'dashboard', component: class {} },
          { path: 'products', component: class {} },
          { path: 'products/:id', component: class {} },
        ]),
        {
          provide: MenuService,
          useValue: {
            isCollapsed: vi.fn().mockReturnValue(false),
            isDisabled: vi.fn().mockReturnValue(false),
            toggleCollapse: vi.fn(),
            toggleOverlayRootCollapse: vi.fn(),
            collapseOverlayRootMenus: vi.fn(),
          },
        },
      ],
    });

    router = TestBed.inject(Router);
    component = TestBed.runInInjectionContext(() => new MenuItemComponent());
    (component as any).item = () => ({
      id: 'products',
      label: 'Products',
      route: '/products',
    });
  });

  it('marks the products route active on the products list route', async () => {
    await router.navigateByUrl('/products');

    expect(component.isActive()).toBe(true);
  });
});
