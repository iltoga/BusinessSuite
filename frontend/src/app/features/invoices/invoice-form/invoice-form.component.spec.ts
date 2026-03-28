import { InvoiceFormComponent } from './invoice-form.component';
import { of } from 'rxjs';
import { vi } from 'vitest';

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

  it('returns list-origin saves back to the invoice list', () => {
    const component = Object.create(InvoiceFormComponent.prototype) as any;
    const invoiceApplications = [];
    component.form = {
      invalid: false,
      value: {
        customer: 9,
        invoiceNo: 'INV-9',
        invoiceDate: new Date('2026-03-27'),
        dueDate: null,
        notes: '',
        sent: false,
        invoiceApplications: [],
      },
      getRawValue: () => ({ customer: 9 }),
      get: (name: string) => (name === 'invoiceApplications' ? { value: invoiceApplications } : null),
      markAllAsTouched: vi.fn(),
    };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.router = { navigate: vi.fn() };
    component.invoicesApi = {
      invoicesCreate: vi.fn().mockReturnValue(of({ id: 44 })),
      invoicesUpdate: vi.fn(),
    };
    component.isSaving = { set: vi.fn() };
    component.isEditMode = () => false;
    component.invoice = () => null;
    component.toIsoDate = vi.fn().mockReturnValue('2026-03-27');

    Object.defineProperty(history, 'state', {
      value: {
        from: 'invoices',
        returnToList: true,
        searchQuery: 'march',
        page: 3,
      },
      writable: true,
    });

    component.save();

    expect(component.router.navigate).toHaveBeenCalledWith(['/invoices'], {
      state: {
        focusTable: true,
        focusId: 44,
        searchQuery: 'march',
        page: 3,
      },
    });
  });
});
