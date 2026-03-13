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
