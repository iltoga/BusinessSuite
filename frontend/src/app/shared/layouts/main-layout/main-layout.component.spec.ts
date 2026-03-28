import { BreakpointObserver } from '@angular/cdk/layout';
import { PLATFORM_ID, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { Router } from '@angular/router';
import { of, Subject } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { ConfigService } from '@/core/services/config.service';
import { ReminderDialogService } from '@/core/services/reminder-dialog.service';
import { ReminderInboxService } from '@/core/services/reminder-inbox.service';
import { ThemeService } from '@/core/services/theme.service';
import { PwaOverlayService } from '@/shared/services/pwa-overlay.service';

import { MainLayoutComponent } from './main-layout.component';

describe('MainLayoutComponent keyboard shortcuts', () => {
  let component: MainLayoutComponent;
  let routerNavigate: ReturnType<typeof vi.fn>;
  let routerEvents$: Subject<unknown>;

  const originalMatchMedia = window.matchMedia;

  beforeAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: vi.fn((query: string) => ({
        matches: query === '(min-width: 768px)' || query === '(min-width: 1024px)',
        media: query,
        onchange: null,
        addEventListener: vi.fn(),
        removeEventListener: vi.fn(),
        addListener: vi.fn(),
        removeListener: vi.fn(),
        dispatchEvent: vi.fn(),
      })),
    });
  });

  afterAll(() => {
    Object.defineProperty(window, 'matchMedia', {
      writable: true,
      value: originalMatchMedia,
    });
  });

  beforeEach(() => {
    routerEvents$ = new Subject<unknown>();
    routerNavigate = vi.fn().mockResolvedValue(true);

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        {
          provide: Router,
          useValue: {
            navigate: routerNavigate,
            events: routerEvents$.asObservable(),
            url: '/dashboard',
          },
        },
        {
          provide: BreakpointObserver,
          useValue: {
            observe: vi.fn().mockReturnValue(of({ matches: true })),
          },
        },
        {
          provide: AuthService,
          useValue: {
            isAdminOrManager: signal(false),
            isSuperuser: signal(false),
            isInAdminGroup: signal(false),
            claims: signal({
              fullName: 'Test User',
              email: 'test@example.com',
              avatar: null,
            }),
            logout: vi.fn(),
          },
        },
        {
          provide: ConfigService,
          useValue: {
            config: signal({
              useOverlayMenu: false,
            }),
          },
        },
        {
          provide: ThemeService,
          useValue: {
            isDarkMode: signal(false),
          },
        },
        {
          provide: ReminderDialogService,
          useValue: {
            enqueueFromInboxReminder: vi.fn(),
          },
        },
        {
          provide: ReminderInboxService,
          useValue: {
            unreadCount: signal(0),
            todayReminders: signal([]),
            isLoading: signal(false),
            start: vi.fn(),
            stop: vi.fn(),
            markRead: vi.fn(),
            markSingleRead: vi.fn(),
          },
        },
        {
          provide: PwaOverlayService,
          useValue: {
            isOverlayMode$: of(false),
          },
        },
      ],
    });

    component = TestBed.runInInjectionContext(() => new MainLayoutComponent());
  });

  afterEach(() => {
    component.ngOnDestroy();
    routerEvents$.complete();
  });

  it('routes Shift+P to Products even when the user is not in the product access role', () => {
    const event = new KeyboardEvent('keydown', {
      key: 'P',
      shiftKey: true,
      bubbles: true,
      cancelable: true,
    });
    const preventDefaultSpy = vi.spyOn(event, 'preventDefault');
    const stopPropagationSpy = vi.spyOn(event, 'stopPropagation');

    (component as any)._capturingKeydown(event);

    expect(preventDefaultSpy).toHaveBeenCalled();
    expect(stopPropagationSpy).toHaveBeenCalled();
    expect(routerNavigate).toHaveBeenCalledWith(['/products']);
  });
});
