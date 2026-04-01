import { of } from 'rxjs';
import { vi } from 'vitest';
import { ensureSourceApplicationIncluded } from './invoice-form-normalizers';
import { InvoiceFormComponent } from './invoice-form.component';

describe('InvoiceFormComponent source application merge', () => {
  it('injects the source application into billable rows when it is still incomplete', () => {
    const rows = [
      {
        product: { id: 10, name: 'KITAS', code: 'KITAS' },
        pendingApplications: [],
        pendingApplicationsCount: 0,
        hasPendingApplications: false,
      },
    ];

    const result = ensureSourceApplicationIncluded(rows as any, {
      id: 314,
      product: { id: 10, name: 'KITAS', code: 'KITAS' },
    });

    expect(
      result[0].pendingApplications.map((application: { id: number }) => application.id),
    ).toEqual([314]);
    expect(result[0].pendingApplicationsCount).toBe(1);
    expect(result[0].hasPendingApplications).toBe(true);
  });

  function buildComponent(overrides: {
    isEditMode?: boolean;
    invoiceId?: number | null;
    createResponseId?: number;
    updateResponseId?: number;
  } = {}) {
    const component = Object.create(InvoiceFormComponent.prototype) as any;
    const invoiceApplications: unknown[] = [];
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
      getRawValue: () => ({
        customer: 9,
        invoiceNo: 'INV-9',
        invoiceDate: new Date('2026-03-27'),
        dueDate: new Date('2026-04-27'),
        notes: '',
        sent: false,
      }),
      get: (name: string) =>
        name === 'invoiceApplications' ? { value: invoiceApplications } : null,
      markAllAsTouched: vi.fn(),
    };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.router = { navigate: vi.fn() };
    component.invoicesApi = {
      invoicesCreate: vi.fn().mockReturnValue(of({ id: overrides.createResponseId ?? 44 })),
      invoicesUpdate: vi.fn().mockReturnValue(of({ id: overrides.updateResponseId ?? 55 })),
    };
    component.isSaving = { set: vi.fn() };
    component.isEditMode = () => overrides.isEditMode ?? false;
    component.invoice = () =>
      overrides.isEditMode ? { id: overrides.invoiceId ?? 54 } : null;

    return component;
  }

  it('redirects create saves to the invoice detail view and preserves origin state', () => {
    const component = buildComponent();

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

    expect(component.router.navigate).toHaveBeenCalledWith(['/invoices', 44], {
      state: {
        from: 'invoices',
        returnUrl: undefined,
        customerId: undefined,
        searchQuery: 'march',
        page: 3,
      },
    });
  });

  it('redirects edit saves to the invoice detail view and preserves origin state', () => {
    const component = buildComponent({ isEditMode: true, invoiceId: 54, updateResponseId: 54 });

    Object.defineProperty(history, 'state', {
      value: {
        from: 'invoices',
        returnToList: true,
        returnUrl: '/invoices/54',
        searchQuery: 'april',
        page: 2,
      },
      writable: true,
    });

    component.save();

    expect(component.invoicesApi.invoicesUpdate).toHaveBeenCalledWith(
      54,
      expect.objectContaining({
        customer: 9,
        invoiceNo: 'INV-9',
      }),
    );
    expect(component.router.navigate).toHaveBeenCalledWith(['/invoices', 54], {
      state: {
        from: 'invoices',
        returnUrl: '/invoices/54',
        customerId: undefined,
        searchQuery: 'april',
        page: 2,
      },
    });
  });
});
