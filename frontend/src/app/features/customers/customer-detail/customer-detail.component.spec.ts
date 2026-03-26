import { signal } from '@angular/core';
import { Subject } from 'rxjs';
import { CustomerDetailComponent } from './customer-detail.component';

describe('CustomerDetailComponent invoice availability', () => {
  it('allows invoice creation for uninvoiced applications regardless of readiness', () => {
    const component = Object.create(CustomerDetailComponent.prototype) as CustomerDetailComponent;

    expect(
      component.canCreateInvoice({
        hasInvoice: false,
        readyForInvoice: false,
      } as never),
    ).toBe(true);
  });

  it('blocks invoice creation when the application already has an invoice', () => {
    const component = Object.create(CustomerDetailComponent.prototype) as CustomerDetailComponent;

    expect(
      component.canCreateInvoice({
        hasInvoice: true,
        readyForInvoice: true,
      } as never),
    ).toBe(false);
  });

  it('shows the passport skeleton whenever a passport file is present', () => {
    const component = Object.create(
      CustomerDetailComponent.prototype,
    ) as CustomerDetailComponent & {
      passportSkeletonVisible: ReturnType<typeof signal<boolean>>;
      setPassportImageLoading: (value: string | null | undefined) => void;
    };

    component.passportSkeletonVisible = signal(false);

    component.setPassportImageLoading('https://example.com/passport.jpg');

    expect(component.passportSkeletonVisible()).toBe(true);
  });

  it('hides the passport skeleton after the image finishes loading', () => {
    const component = Object.create(
      CustomerDetailComponent.prototype,
    ) as CustomerDetailComponent & {
      passportSkeletonVisible: ReturnType<typeof signal<boolean>>;
    };

    component.passportSkeletonVisible = signal(true);

    component.onPassportImageLoaded();

    expect(component.passportSkeletonVisible()).toBe(false);
  });

  it('keeps the detail view loading until both customer and history requests complete', () => {
    const component = Object.create(
      CustomerDetailComponent.prototype,
    ) as CustomerDetailComponent & {
      item: ReturnType<typeof signal<any>>;
      applicationsHistory: ReturnType<typeof signal<any[]>>;
      isLoading: ReturnType<typeof signal<boolean>>;
      goBack: () => void;
    };

    const customer$ = new Subject<any>();
    const history$ = new Subject<any[]>();
    const toastError = vi.fn();

    component.item = signal(null);
    component.applicationsHistory = signal([]);
    component.isLoading = signal(false);
    component.goBack = vi.fn();

    Object.defineProperty(component, 'customersService', {
      value: {
        getCustomer: vi.fn(() => customer$),
        getApplicationsHistory: vi.fn(() => history$),
      },
      configurable: true,
    });
    Object.defineProperty(component, 'toast', {
      value: { error: toastError },
      configurable: true,
    });

    (component as any).loadCustomerAndHistory(3);

    expect(component.isLoading()).toBe(true);

    history$.next([{ id: 10 }]);
    history$.complete();

    expect(component.isLoading()).toBe(true);
    expect(component.item()).toBeNull();

    customer$.next({ id: 3, fullName: 'Daniel Frankel' });
    customer$.complete();

    expect(component.isLoading()).toBe(false);
    expect(component.item()).toMatchObject({ id: 3 });
    expect(component.applicationsHistory()).toEqual([{ id: 10 }]);
    expect(toastError).not.toHaveBeenCalled();
  });
});
