import type { InvoiceApplicationDetail } from '@/core/api';
import { InvoiceDetailComponent } from './invoice-detail.component';

describe('InvoiceDetailComponent invoice line helpers', () => {
  it('returns a safe positive quantity for invoice lines', () => {
    const component = Object.create(InvoiceDetailComponent.prototype) as InvoiceDetailComponent;

    expect(
      component.getApplicationQuantity({ quantity: 3 } as InvoiceApplicationDetail & { quantity: number }),
    ).toBe(3);
    expect(
      component.getApplicationQuantity({ quantity: 0 } as InvoiceApplicationDetail & { quantity: number }),
    ).toBe(1);
  });

  it('returns line notes when present and null for blank values', () => {
    const component = Object.create(InvoiceDetailComponent.prototype) as InvoiceDetailComponent;

    expect(
      component.getApplicationNotes({
        notes: '  Customer-specific note  ',
      } as InvoiceApplicationDetail & { notes: string }),
    ).toBe('  Customer-specific note  ');
    expect(
      component.getApplicationNotes({ notes: '   ' } as InvoiceApplicationDetail & { notes: string }),
    ).toBeNull();
  });

  it('formats linked application titles from the linked customer application', () => {
    const component = Object.create(InvoiceDetailComponent.prototype) as InvoiceDetailComponent;

    expect(
      component.getLinkedApplicationTitle({
        id: 280,
        product: {
          code: 'XVOA',
          name: 'VOA Extension (30 Days)',
        },
      } as NonNullable<InvoiceApplicationDetail['customerApplication']>),
    ).toBe('Application #280 - XVOA - VOA Extension (30 Days)');
  });

  it('detects visa products without linked applications so the placeholder can be shown', () => {
    const component = Object.create(InvoiceDetailComponent.prototype) as InvoiceDetailComponent;

    expect(
      component.isVisaProduct({
        product: {
          productType: 'visa',
        },
      } as InvoiceApplicationDetail),
    ).toBe(true);
    expect(component.hasLinkedApplication({ customerApplication: null } as InvoiceApplicationDetail)).toBe(
      false,
    );
  });
});
