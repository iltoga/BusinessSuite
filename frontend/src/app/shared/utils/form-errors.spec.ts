import { FormBuilder } from '@angular/forms';
import { applyServerErrorsToForm } from './form-errors';

describe('form-errors utilities', () => {
  const fb = new FormBuilder();

  it('applies DRF-style field errors to controls', () => {
    const form = fb.group({ passport_number: [''] });

    const payload = {
      errors: { passport_number: ['This passport number is already used by another customer.'] },
    };

    applyServerErrorsToForm(form, payload);

    const err = form.get('passport_number')?.errors?.['server'];
    expect(err).toBe('This passport number is already used by another customer.');
  });

  it('applies quick-create style errors to controls', () => {
    const form = fb.group({ passport_number: [''] });

    const payload = {
      success: false,
      errors: { passport_number: ['This passport number is already used by another customer.'] },
    };

    applyServerErrorsToForm(form, payload);

    const err = form.get('passport_number')?.errors?.['server'];
    expect(err).toBe('This passport number is already used by another customer.');
  });
});
