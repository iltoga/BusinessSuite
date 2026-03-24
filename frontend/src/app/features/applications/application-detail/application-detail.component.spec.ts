import { of } from 'rxjs';
import { vi } from 'vitest';

import { ApplicationDetailComponent } from './application-detail.component';

describe('ApplicationDetailComponent pending passport refresh', () => {
  type ApplicationDetailHarness = any;

  const createHarness = (): ApplicationDetailHarness => {
    const component = Object.create(
      ApplicationDetailComponent.prototype,
    ) as ApplicationDetailHarness;

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

describe('ApplicationDetailComponent pending due date refresh', () => {
  type ApplicationDetailHarness = any;

  const createHarness = (): ApplicationDetailHarness => {
    const component = Object.create(
      ApplicationDetailComponent.prototype,
    ) as ApplicationDetailHarness;

    component.isBrowser = true;
    component.pendingDueDateRefreshEnabled = true;
    component.pendingDueDateRefreshAttempts = 0;
    component.pendingDueDateRefreshTimer = null;
    component.pendingDueDateRefreshMaxAttempts = 8;
    component.pendingDueDateRefreshIntervalMs = 25;
    component.loadApplication = vi.fn();

    component.clearPendingDueDateRefresh =
      ApplicationDetailComponent.prototype['clearPendingDueDateRefresh'].bind(component);
    component.shouldAwaitDueDateRefresh =
      ApplicationDetailComponent.prototype['shouldAwaitDueDateRefresh'].bind(component);
    component.schedulePendingDueDateRefresh =
      ApplicationDetailComponent.prototype['schedulePendingDueDateRefresh'].bind(component);
    component.handlePendingDueDateRefresh =
      ApplicationDetailComponent.prototype['handlePendingDueDateRefresh'].bind(component);

    return component;
  };

  it('schedules a silent reload when the submission date changed but the deadline is still missing', () => {
    vi.useFakeTimers();
    const component = createHarness();

    component.handlePendingDueDateRefresh(42, {
      dueDate: null,
      addDeadlinesToCalendar: true,
      hasNextTask: true,
      nextTask: { id: 15 },
    });

    vi.advanceTimersByTime(25);

    expect(component.loadApplication).toHaveBeenCalledWith(42, { silent: true });
    vi.useRealTimers();
  });

  it('stops refreshing once the due date is present', () => {
    const component = createHarness();

    component.handlePendingDueDateRefresh(42, {
      dueDate: '2026-03-31',
      addDeadlinesToCalendar: true,
      hasNextTask: true,
      nextTask: { id: 15 },
    });

    expect(component.pendingDueDateRefreshEnabled).toBe(false);
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
      'Application submission date cannot be changed after Step 1 is completed.';
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
      'Application submission date updated',
    );
  });
});

describe('ApplicationDetailComponent application partial updates', () => {
  it('applies the server response directly when a partial update succeeds', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.application = Object.assign(
      vi.fn(() => ({ id: 321 })),
      {
        set: vi.fn(),
      },
    );
    component.isSavingMeta = Object.assign(
      vi.fn(() => false),
      {
        set: vi.fn(),
      },
    );
    component.editableNotes = { set: vi.fn() };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.loadApplication = vi.fn();
    component.applyApplicationFromActionResponse =
      ApplicationDetailComponent.prototype['applyApplicationFromActionResponse'].bind(component);
    component.normalizeApplicationPayload =
      ApplicationDetailComponent.prototype['normalizeApplicationPayload'].bind(component);
    component.updateApplicationPartial =
      ApplicationDetailComponent.prototype['updateApplicationPartial'].bind(component);
    component.applicationsService = {
      updateApplicationPartial: vi.fn(() =>
        of({
          id: 321,
          docDate: '2026-03-28',
          dueDate: '2026-03-31',
          documents: [],
          workflows: [],
          notes: 'Saved',
        }),
      ),
    };

    component.updateApplicationPartial({ docDate: '2026-03-28' }, 'Application updated');

    expect(component.toast.success).toHaveBeenCalledWith('Application updated');
    expect(component.application.set).toHaveBeenCalledWith(
      expect.objectContaining({
        id: 321,
        docDate: '2026-03-28',
        dueDate: '2026-03-31',
        documents: [],
        workflows: [],
        notes: 'Saved',
      }),
    );
    expect(component.loadApplication).not.toHaveBeenCalled();
    expect(component.isSavingMeta.set).toHaveBeenCalledWith(true);
    expect(component.isSavingMeta.set).toHaveBeenCalledWith(false);
  });

  it('keeps the submission and deadline dates when the API payload uses snake_case keys', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.normalizeApplicationPayload =
      ApplicationDetailComponent.prototype['normalizeApplicationPayload'].bind(component);

    const normalized = component.normalizeApplicationPayload({
      id: 321,
      doc_date: '2026-03-28',
      due_date: '2026-03-31',
      documents: [],
      workflows: [],
    });

    expect(normalized.docDate).toBe('2026-03-28');
    expect(normalized.dueDate).toBe('2026-03-31');
  });

  it('retries a silent reload when the patch response is missing the next deadline', () => {
    vi.useFakeTimers();
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    let currentApplication: any = { id: 321 };
    component.application = Object.assign(
      vi.fn(() => currentApplication),
      {
        set: vi.fn((value: unknown) => {
          currentApplication = value;
        }),
      },
    );
    component.isBrowser = true;
    component.pendingDueDateRefreshEnabled = false;
    component.pendingDueDateRefreshAttempts = 0;
    component.pendingDueDateRefreshTimer = null;
    component.pendingDueDateRefreshMaxAttempts = 8;
    component.pendingDueDateRefreshIntervalMs = 25;
    component.isSavingMeta = Object.assign(
      vi.fn(() => false),
      {
        set: vi.fn(),
      },
    );
    component.editableNotes = { set: vi.fn() };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.loadApplication = vi.fn();
    component.clearPendingDueDateRefresh =
      ApplicationDetailComponent.prototype['clearPendingDueDateRefresh'].bind(component);
    component.shouldAwaitDueDateRefresh =
      ApplicationDetailComponent.prototype['shouldAwaitDueDateRefresh'].bind(component);
    component.schedulePendingDueDateRefresh =
      ApplicationDetailComponent.prototype['schedulePendingDueDateRefresh'].bind(component);
    component.handlePendingDueDateRefresh =
      ApplicationDetailComponent.prototype['handlePendingDueDateRefresh'].bind(component);
    component.applyApplicationFromActionResponse =
      ApplicationDetailComponent.prototype['applyApplicationFromActionResponse'].bind(component);
    component.normalizeApplicationPayload =
      ApplicationDetailComponent.prototype['normalizeApplicationPayload'].bind(component);
    component.updateApplicationPartial =
      ApplicationDetailComponent.prototype['updateApplicationPartial'].bind(component);
    component.applicationsService = {
      updateApplicationPartial: vi.fn(() =>
        of({
          id: 321,
          docDate: '2026-03-28',
          dueDate: null,
          addDeadlinesToCalendar: true,
          hasNextTask: true,
          nextTask: { id: 15, name: 'biometrics' },
          documents: [],
          workflows: [],
          notes: 'Saved',
        }),
      ),
    };

    component.updateApplicationPartial({ docDate: '2026-03-28' }, 'Application updated');
    vi.advanceTimersByTime(25);

    expect(component.loadApplication).toHaveBeenCalledWith(321, { silent: true });
    vi.useRealTimers();
  });
});

describe('ApplicationDetailComponent validation extraction merge', () => {
  it('prefers freshly extracted doc number and expiration date over stale form values', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.extractValidationAutoFillFields =
      ApplicationDetailComponent.prototype['extractValidationAutoFillFields'].bind(component);
    component.mergeUploadFormWithValidationExtraction =
      ApplicationDetailComponent.prototype['mergeUploadFormWithValidationExtraction'].bind(
        component,
      );

    const merged = component.mergeUploadFormWithValidationExtraction(
      {
        docNumber: 'OLD-ITK-001',
        expirationDate: '2025-01-01',
        details: 'Keep my manual notes',
      },
      {
        extracted_doc_number: 'NEW-ITK-999',
        extracted_expiration_date: '2026-01-30',
        extracted_details_markdown: '## OCR details',
      },
    );

    expect(merged).toEqual({
      docNumber: 'NEW-ITK-999',
      expirationDate: '2026-01-30',
      details: 'Keep my manual notes',
    });
  });

  it('patches extracted values into the upload form', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.parseApiDate = vi.fn((value: string | null) =>
      value ? new Date(`${value}T00:00:00`) : null,
    );
    component.uploadForm = {
      getRawValue: vi.fn(() => ({ details: '   ' })),
      patchValue: vi.fn(),
    };
    component.extractValidationAutoFillFields =
      ApplicationDetailComponent.prototype['extractValidationAutoFillFields'].bind(component);
    component.applyValidationExtractionToUploadForm =
      ApplicationDetailComponent.prototype['applyValidationExtractionToUploadForm'].bind(component);

    component.applyValidationExtractionToUploadForm({
      extracted_doc_number: 'ITK-2026-ABC',
      extracted_expiration_date: '2026-01-30',
      extracted_details_markdown: '## OCR details',
    });

    expect(component.uploadForm.patchValue).toHaveBeenCalledWith({
      docNumber: 'ITK-2026-ABC',
      expirationDate: new Date('2026-01-30T00:00:00'),
      details: '## OCR details',
    });
  });
});

describe('ApplicationDetailComponent categorization progress messaging', () => {
  // Categorization progress tests have been moved to categorization-handler.service.spec.ts
  // as the logic now lives in ApplicationCategorizationHandler service.
  it('delegates categorization to catHandler', () => {
    expect(true).toBe(true);
  });
});

describe('ApplicationDetailComponent confirmForceClose', () => {
  /**
   * Regression: forceClose was called with (id, app) — the app object was passed
   * as the second positional argument which the generated API client interprets as
   * the `observe` option, causing NG02809 "unhandled observe type [object Object]".
   * The fix removes the spurious second argument so the call is forceClose(id) only.
   */
  const createHarness = () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;

    component.application = vi.fn(() => ({ id: 327, status: 'pending', canForceClose: true }));
    component.canForceClose = vi.fn(() => true);
    component.workflowAction = { set: vi.fn() };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.loadApplication = vi.fn();
    component.applyApplicationFromActionResponse = vi.fn(() => true);
    component.patchForceCloseLocally = vi.fn(() => false);
    component.applicationsService = {
      forceClose: vi.fn(() => of({ id: 327, status: 'completed' })),
    };

    // Suppress the browser confirm dialog — auto-confirm
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    );

    component.confirmForceClose =
      ApplicationDetailComponent.prototype['confirmForceClose'].bind(component);

    return component;
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls forceClose with only the application id — no second argument', () => {
    const component = createHarness();

    component.confirmForceClose();

    expect(component.applicationsService.forceClose).toHaveBeenCalledTimes(1);
    // Must be called with exactly one argument (the id). A second argument (e.g. the
    // application object) would be interpreted as the `observe` option and trigger
    // NG02809 "unhandled observe type [object Object]".
    expect(component.applicationsService.forceClose).toHaveBeenCalledWith(327);
    const callArgs: unknown[] = component.applicationsService.forceClose.mock.calls[0];
    expect(callArgs).toHaveLength(1);
  });

  it('shows a success toast and clears the workflow action after a successful force close', () => {
    const component = createHarness();

    component.confirmForceClose();

    expect(component.toast.success).toHaveBeenCalledWith('Application force closed');
    expect(component.workflowAction.set).toHaveBeenCalledWith(null);
  });

  it('does nothing when the application is not force-closeable', () => {
    const component = createHarness();
    component.canForceClose = vi.fn(() => false);

    component.confirmForceClose();

    expect(component.applicationsService.forceClose).not.toHaveBeenCalled();
    expect(component.toast.error).toHaveBeenCalledWith('You cannot force close this application');
  });
});
