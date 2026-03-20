import { Location } from '@angular/common';
import { TestBed } from '@angular/core/testing';
import { ActivatedRoute, Router } from '@angular/router';
import { describe, expect, it, vi, beforeEach, afterEach } from 'vitest';

import { FormNavigationFacadeService } from './form-navigation-facade.service';

const createRouterMock = () => ({
  navigate: vi.fn(() => Promise.resolve(true)),
  navigateByUrl: vi.fn(() => Promise.resolve(true)),
  getCurrentNavigation: vi.fn(() => ({ extras: { state: null as any } })),
});

describe('FormNavigationFacadeService', () => {
  let service: FormNavigationFacadeService;
  let routerMock: ReturnType<typeof createRouterMock>;
  let locationMock: { back: ReturnType<typeof vi.fn> };
  let routeMock: { snapshot: { paramMap: { get: ReturnType<typeof vi.fn> } } };

  beforeEach(() => {
    routerMock = createRouterMock();
    locationMock = { back: vi.fn() };
    routeMock = {
      snapshot: {
        paramMap: {
          get: vi.fn(() => null),
        },
      },
    };

    window.history.replaceState({}, '', window.location.href);

    TestBed.configureTestingModule({
      providers: [
        FormNavigationFacadeService,
        { provide: Router, useValue: routerMock },
        { provide: Location, useValue: locationMock },
        { provide: ActivatedRoute, useValue: routeMock },
      ],
    });

    service = TestBed.inject(FormNavigationFacadeService);
  });

  afterEach(() => {
    vi.restoreAllMocks();
    TestBed.resetTestingModule();
  });

  it('returns to the originating applications list when the route state says so', () => {
    const originalHistory = window.history;
    Object.defineProperty(window, 'history', {
      configurable: true,
      value: {
        length: 1,
        state: {
          from: 'applications',
          focusId: 9,
          searchQuery: 'visa',
          page: 3,
        },
      },
    });

    try {
      routerMock.getCurrentNavigation.mockReturnValue({
        extras: {
          state: {
            from: 'applications',
            focusId: 9,
            searchQuery: 'visa',
            page: 3,
          },
        },
      });

      service.goBackFromApplicationForm({
        router: routerMock as any,
        route: routeMock as any,
        location: locationMock as any,
        applicationId: 17,
        isEditMode: true,
        selectedCustomerId: null,
      });

      expect(routerMock.navigate).toHaveBeenCalledWith(['/applications'], {
        state: {
          focusTable: true,
          focusId: 9,
          searchQuery: 'visa',
          page: 3,
        },
      });
    } finally {
      Object.defineProperty(window, 'history', {
        configurable: true,
        value: originalHistory,
      });
    }
  });

  it('uses browser history when available before falling back to route navigation', () => {
    routerMock.getCurrentNavigation.mockReturnValue({ extras: { state: {} } });
    const originalHistory = window.history;
    Object.defineProperty(window, 'history', {
      configurable: true,
      value: { length: 2 },
    });

    service.goBackFromApplicationForm({
      router: routerMock as any,
      route: routeMock as any,
      location: locationMock as any,
      applicationId: 17,
      isEditMode: true,
      selectedCustomerId: null,
    });

    expect(locationMock.back).toHaveBeenCalled();
    expect(routerMock.navigate).not.toHaveBeenCalled();

    Object.defineProperty(window, 'history', {
      configurable: true,
      value: originalHistory,
    });
  });

  it('falls back to the customer detail route when a customer id is available', () => {
    routerMock.getCurrentNavigation.mockReturnValue({ extras: { state: {} } });
    routeMock.snapshot.paramMap.get.mockReturnValue('42');

    service.goBackFromApplicationForm({
      router: routerMock as any,
      route: routeMock as any,
      location: locationMock as any,
      applicationId: 17,
      isEditMode: true,
      selectedCustomerId: null,
    });

    expect(routerMock.navigate).toHaveBeenCalledWith(['/customers', 42]);
  });

  it('falls back to the application detail route when editing and no return path is available', () => {
    routerMock.getCurrentNavigation.mockReturnValue({ extras: { state: {} } });

    service.goBackFromApplicationForm({
      router: routerMock as any,
      route: routeMock as any,
      location: locationMock as any,
      applicationId: 17,
      isEditMode: true,
      selectedCustomerId: null,
    });

    expect(routerMock.navigate).toHaveBeenCalledWith(['/applications', 17]);
  });

  it('uses returnUrl for invoice forms and preserves search/page state', () => {
    service.goBackFromInvoiceForm({
      router: routerMock as any,
      state: { returnUrl: '/applications/17', searchQuery: 'abc', page: 2 },
      invoiceId: 99,
    });

    expect(routerMock.navigateByUrl).toHaveBeenCalledWith('/applications/17', {
      state: {
        searchQuery: 'abc',
        page: 2,
      },
    });
  });

  it('navigates back to invoices by default for invoice forms', () => {
    service.goBackFromInvoiceForm({
      router: routerMock as any,
      state: {},
      invoiceId: 99,
    });

    expect(routerMock.navigate).toHaveBeenCalledWith(['/invoices'], {
      state: {
        focusTable: true,
        focusId: 99,
      },
    });
  });
});
