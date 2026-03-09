import { InvoiceFormComponent } from './invoice-form.component';

describe('InvoiceFormComponent source application merge', () => {
  it('injects the source application into billable rows when it is still incomplete', () => {
    const component = Object.create(InvoiceFormComponent.prototype) as any;
    component.sortBillableRows = InvoiceFormComponent.prototype['sortBillableRows'].bind(component);
    component.ensureSourceApplicationIncluded =
      InvoiceFormComponent.prototype['ensureSourceApplicationIncluded'].bind(component);

    const rows = [
      {
        product: { id: 10, name: 'KITAS', code: 'KITAS' },
        pendingApplications: [],
        pendingApplicationsCount: 0,
        hasPendingApplications: false,
      },
    ];

    const result = component.ensureSourceApplicationIncluded(rows, {
      id: 314,
      product: { id: 10, name: 'KITAS', code: 'KITAS' },
    });

    expect(result[0].pendingApplications.map((application: { id: number }) => application.id)).toEqual([314]);
    expect(result[0].pendingApplicationsCount).toBe(1);
    expect(result[0].hasPendingApplications).toBe(true);
  });
});
