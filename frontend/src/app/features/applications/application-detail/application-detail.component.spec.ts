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
