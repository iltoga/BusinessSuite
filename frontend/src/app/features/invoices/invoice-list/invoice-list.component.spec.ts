import { PLATFORM_ID, signal } from '@angular/core';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { of } from 'rxjs';

import { InvoicesService } from '@/core/api';
import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';

import { InvoiceListComponent } from './invoice-list.component';

describe('InvoiceListComponent keyboard shortcuts', () => {
  let component: InvoiceListComponent;
  let previewSpy: ReturnType<typeof vi.fn>;
  let selectedRow: { id: number };

  beforeEach(() => {
    vi.useFakeTimers();
    sessionStorage.clear();
    selectedRow = { id: 7 };
    previewSpy = vi.fn();

    TestBed.configureTestingModule({
      providers: [
        { provide: PLATFORM_ID, useValue: 'browser' },
        {
          provide: Router,
          useValue: {
            navigate: vi.fn(),
            getCurrentNavigation: vi.fn().mockReturnValue(null),
          },
        },
        {
          provide: ActivatedRoute,
          useValue: { snapshot: { queryParams: {} } },
        },
        {
          provide: InvoicesService,
          useValue: {
            invoicesList: vi.fn().mockReturnValue(of({ count: 0, results: [] })),
          },
        },
        {
          provide: AuthService,
          useValue: {
            isSuperuser: signal(false),
            isAdmin: signal(false),
            isInAdminGroup: signal(false),
            claims: signal({ fullName: 'Test User' }),
          },
        },
        {
          provide: GlobalToastService,
          useValue: {
            success: vi.fn(),
            error: vi.fn(),
            info: vi.fn(),
            loading: vi.fn(),
          },
        },
      ],
    });

    component = TestBed.runInInjectionContext(() => new InvoiceListComponent());
    (component as any).focusAfterLoad = vi.fn();
    (component as any).dataTable = () => ({
      selectedRow: () => selectedRow,
      focusRowById: vi.fn(),
      focusFirstRowIfNone: vi.fn(),
    });
    (component as any).rowDownloadDropdowns = () => [
      {
        invoiceId: () => selectedRow.id,
        openPrintPreview: previewSpy,
      },
    ];

    vi.runOnlyPendingTimers();
  });

  afterEach(() => {
    vi.runOnlyPendingTimers();
    vi.useRealTimers();
    sessionStorage.clear();
  });

  it('ignores Shift+P so the global product shortcut can win', () => {
    component.handleGlobalKeydown(
      new KeyboardEvent('keydown', {
        key: 'P',
        shiftKey: true,
        bubbles: true,
        cancelable: true,
      }),
    );

    expect(previewSpy).not.toHaveBeenCalled();
  });

  it('still opens print preview on plain P', () => {
    component.handleGlobalKeydown(
      new KeyboardEvent('keydown', {
        key: 'P',
        bubbles: true,
        cancelable: true,
      }),
    );

    expect(previewSpy).toHaveBeenCalledTimes(1);
  });
});
