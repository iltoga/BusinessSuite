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
});
