import { vi } from 'vitest';

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
});

describe('CustomerDetailComponent navigation', () => {
  it('returns to the stored route when opened from another detail page', () => {
    const component = Object.create(CustomerDetailComponent.prototype) as any;
    component.returnUrl = () => '/applications/314';
    component.returnState = () => ({ from: 'applications', focusId: 314, page: 2 });
    component.originSearchQuery = () => 'stefano';
    component.originPage = () => 2;
    component.customer = () => ({ id: 99 });
    component.router = { navigate: vi.fn(), navigateByUrl: vi.fn() };

    component.goBack();

    expect(component.router.navigateByUrl).toHaveBeenCalledWith('/applications/314', {
      state: { from: 'applications', focusId: 314, page: 2 },
    });
    expect(component.router.navigate).not.toHaveBeenCalled();
  });
});
