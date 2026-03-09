import { vi } from 'vitest';

import { ApplicationDetailComponent } from './application-detail.component';

describe('ApplicationDetailComponent pending passport refresh', () => {
  type ApplicationDetailHarness = any;

  const createHarness = (): ApplicationDetailHarness => {
    const component = Object.create(ApplicationDetailComponent.prototype) as ApplicationDetailHarness;

    component.isBrowser = true;
    component.pendingPassportRefreshEnabled = true;
    component.pendingPassportRefreshAttempts = 0;
    component.pendingPassportRefreshTimer = null;
    component.pendingPassportRefreshMaxAttempts = 10;
    component.pendingPassportRefreshIntervalMs = 25;
    component.loadApplication = vi.fn();

    component.parseDocumentNames =
      ApplicationDetailComponent.prototype['parseDocumentNames'].bind(component);
    component.getConfiguredDocumentNames =
      ApplicationDetailComponent.prototype['getConfiguredDocumentNames'].bind(component);
    component.isPassportConfigured =
      ApplicationDetailComponent.prototype['isPassportConfigured'].bind(component);
    component.hasPassportDocument =
      ApplicationDetailComponent.prototype['hasPassportDocument'].bind(component);
    component.clearPendingPassportRefresh =
      ApplicationDetailComponent.prototype['clearPendingPassportRefresh'].bind(component);
    component.schedulePendingPassportRefresh =
      ApplicationDetailComponent.prototype['schedulePendingPassportRefresh'].bind(component);
    component.handlePendingPassportRefresh =
      ApplicationDetailComponent.prototype['handlePendingPassportRefresh'].bind(component);

    return component;
  };

  it('schedules a silent reload when passport is configured but not yet present', () => {
    vi.useFakeTimers();
    const component = createHarness();

    component.handlePendingPassportRefresh(42, {
      product: { requiredDocuments: 'Passport' },
      documents: [],
    });

    vi.advanceTimersByTime(25);

    expect(component.loadApplication).toHaveBeenCalledWith(42, { silent: true });
    vi.useRealTimers();
  });

  it('stops refreshing once the passport document exists', () => {
    const component = createHarness();

    component.handlePendingPassportRefresh(42, {
      product: { requiredDocuments: 'Passport' },
      documents: [{ docType: { name: 'Passport' } }],
    });

    expect(component.pendingPassportRefreshEnabled).toBe(false);
    expect(component.loadApplication).not.toHaveBeenCalled();
  });
});

describe('ApplicationDetailComponent invoice availability', () => {
  it('allows invoice creation for uninvoiced applications regardless of readiness', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.application = () => ({
      hasInvoice: false,
      readyForInvoice: false,
    });

    expect(component.canCreateInvoice()).toBe(true);
  });

  it('blocks invoice creation when an invoice already exists', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.application = () => ({
      hasInvoice: true,
      readyForInvoice: true,
    });

    expect(component.canCreateInvoice()).toBe(false);
  });
});

describe('ApplicationDetailComponent customer navigation', () => {
  it('builds customer detail navigation state with a return target to the application', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.isBrowser = false;
    component.application = () => ({
      id: 314,
      customer: { id: 99 },
    });
    component.originSearchQuery = () => 'stefano';
    component.originPage = () => 2;

    expect(component.customerDetailState()).toEqual({
      from: 'application-detail',
      applicationId: 314,
      customerId: 99,
      returnUrl: '/applications/314',
      returnState: {},
      searchQuery: 'stefano',
      page: 2,
    });
  });
});

describe('ApplicationDetailComponent inline application date editing', () => {
  const createHarness = () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.toast = { error: vi.fn() };
    component.applicationDateLockedTooltip =
      'Application date cannot be changed after Step 1 is completed.';
    component.dueDateLockedTooltip =
      'Please update Due date in Task Timeline to change this deadline.';
    component.isApplicationDateLocked = vi.fn(() => false);
    component.isDueDateLocked = vi.fn(() => false);
    component.stayPermitSubmissionWindow = vi.fn(() => null);
    component.formatDateForApi = vi.fn(() => '2026-03-13');
    component.updateApplicationPartial = vi.fn();
    component.onInlineDateChange =
      ApplicationDetailComponent.prototype.onInlineDateChange.bind(component);
    return component;
  };

  it('blocks application date changes when step 1 is completed', () => {
    const component = createHarness();
    component.isApplicationDateLocked = vi.fn(() => true);

    component.onInlineDateChange('docDate', new Date('2026-03-13'));

    expect(component.toast.error).toHaveBeenCalledWith(component.applicationDateLockedTooltip);
    expect(component.updateApplicationPartial).not.toHaveBeenCalled();
  });

  it('updates the application date when step 1 is still open', () => {
    const component = createHarness();

    component.onInlineDateChange('docDate', new Date('2026-03-13'));

    expect(component.updateApplicationPartial).toHaveBeenCalledWith(
      { docDate: '2026-03-13' },
      'Application date updated',
    );
  });
});
