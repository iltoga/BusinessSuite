import { FormBuilder } from '@angular/forms';
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
    const invoiceApplications: unknown[] = [
      {
        id: 71,
        product: 11,
        customerApplication: 21,
        quantity: 2,
        notes: ' Line note ',
        amount: 350000,
      },
      {
        id: 72,
        product: 12,
        customerApplication: null,
        quantity: 1,
        notes: '',
        amount: 125000,
      },
    ];
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
        invoiceApplications,
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

    expect(component.invoicesApi.invoicesCreate).toHaveBeenCalledWith(
      expect.objectContaining({
        invoiceApplications: [
          {
            id: 71,
            product: 11,
            customerApplication: 21,
            quantity: 2,
            notes: ' Line note ',
            amount: '350000',
          },
          {
            id: 72,
            product: 12,
            customerApplication: null,
            quantity: 1,
            notes: null,
            amount: '125000',
          },
        ],
      }),
    );
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
        invoiceApplications: [
          {
            id: 71,
            product: 11,
            customerApplication: 21,
            quantity: 2,
            notes: ' Line note ',
            amount: '350000',
          },
          {
            id: 72,
            product: 12,
            customerApplication: null,
            quantity: 1,
            notes: null,
            amount: '125000',
          },
        ],
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

  it('recomputes amount from qty while the line has not been manually overridden', () => {
    const component = Object.create(InvoiceFormComponent.prototype) as any;
    const fb = new FormBuilder();
    const group = fb.group({
      product: [19],
      customerApplication: [null],
      quantity: [3],
      amount: [150],
      amountOverridden: [false],
    });

    component.findPendingApplicationById = vi.fn().mockReturnValue(undefined);
    component.resolveProductPrice = vi.fn().mockReturnValue(150);
    component['onLineQuantityChanged'](group, 3);

    expect(group.get('amount')?.value).toBe(450);
  });

  it('keeps a custom amount when qty changes after manual override', () => {
    const component = Object.create(InvoiceFormComponent.prototype) as any;
    const fb = new FormBuilder();
    const group = fb.group({
      product: [19],
      customerApplication: [null],
      quantity: [4],
      amount: [999],
      amountOverridden: [true],
    });

    component.findPendingApplicationById = vi.fn().mockReturnValue(undefined);
    component.resolveProductPrice = vi.fn().mockReturnValue(150);
    component['onLineQuantityChanged'](group, 4);

    expect(group.get('amount')?.value).toBe(999);
  });

  it('updates the total amount signal when line amounts change', () => {
    const component = Object.create(InvoiceFormComponent.prototype) as any;
    const fb = new FormBuilder();
    component.totalAmount = {
      set: vi.fn(),
    };
    component.form = fb.group({
      invoiceApplications: fb.array([
        fb.group({ amount: [950000] }),
        fb.group({ amount: [39750000] }),
      ]),
    });

    component['updateTotalAmount']();

    expect(component.totalAmount.set).toHaveBeenCalledWith(40700000);
  });
});
