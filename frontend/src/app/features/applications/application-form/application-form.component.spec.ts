import { of } from 'rxjs';
import { vi } from 'vitest';

import { ApplicationFormComponent } from './application-form.component';

describe('ApplicationFormComponent save redirects', () => {
  it('returns list-origin saves back to the applications list', () => {
    const component = Object.create(ApplicationFormComponent.prototype) as any;
    component.form = {
      invalid: false,
      value: {
        product: 5,
        docDate: new Date('2026-03-27'),
        dueDate: null,
        addDeadlinesToCalendar: false,
        notifyCustomer: false,
        notifyCustomerChannel: null,
        notes: '',
        documents: [],
      },
      getRawValue: () => ({ customer: 11 }),
      markAllAsTouched: vi.fn(),
    };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.router = { navigate: vi.fn() };
    component.customerApplicationsService = {
      customerApplicationsCreate: vi.fn().mockReturnValue(of({ id: 22 })),
      customerApplicationsPartialUpdate: vi.fn(),
    };
    component.isSubmitting = { set: vi.fn() };
    component.isEditMode = () => false;
    component.applicationId = () => null;
    component.toApiDate = vi.fn().mockReturnValue('2026-03-27');
    component.shouldAwaitPassportImport = vi.fn().mockReturnValue(false);

    Object.defineProperty(history, 'state', {
      value: {
        from: 'applications',
        returnToList: true,
        searchQuery: 'pending',
        page: 4,
      },
      writable: true,
    });

    component.submit();

    expect(component.router.navigate).toHaveBeenCalledWith(['/applications'], {
      state: {
        focusTable: true,
        focusId: 22,
        searchQuery: 'pending',
        page: 4,
      },
    });
  });
});
