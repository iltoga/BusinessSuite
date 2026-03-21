import { signal } from '@angular/core';
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
});
