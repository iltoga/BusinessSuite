import { FormBuilder } from '@angular/forms';
import { applyServerErrorsToForm, extractServerErrorMessage } from './form-errors';

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

  it('supports canonical error envelopes with message and details', () => {
    const form = fb.group({ passport_number: [''] });

    const payload = {
      error: {
        code: 'validation_error',
        message: 'Validation error',
        details: {
          passport_number: ['This passport number is already used by another customer.'],
        },
      },
      meta: {
        request_id: 'req-1',
        api_version: 'v1',
      },
    };

    applyServerErrorsToForm(form, payload);

    const err = form.get('passport_number')?.errors?.['server'];
    expect(err).toBe('This passport number is already used by another customer.');
    expect(extractServerErrorMessage(payload)).toBe(
      'This passport number is already used by another customer.',
    );
  });
});
