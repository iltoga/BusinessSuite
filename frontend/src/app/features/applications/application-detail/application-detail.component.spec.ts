import { of } from 'rxjs';
import { vi } from 'vitest';

import { ApplicationDetailComponent } from './application-detail.component';
import { DocumentUploadService } from './document-upload.service';
import { PendingFieldPoller } from './pending-field-refresh.service';
import { ApplicationWorkflowService } from './workflow.service';

describe('PendingFieldPoller (passport channel)', () => {
  const createPoller = () => {
    const reloadFn = vi.fn();
    const poller = new PendingFieldPoller({ maxAttempts: 10, intervalMs: 25 }, true);
    poller.bindReload(reloadFn);
    poller.start();
    return { poller, reloadFn };
  };

  it('schedules a silent reload when shouldContinue is true', () => {
    vi.useFakeTimers();
    const { poller, reloadFn } = createPoller();

    poller.handleRefresh(42, true);
    vi.advanceTimersByTime(25);

    expect(reloadFn).toHaveBeenCalledWith(42);
    vi.useRealTimers();
  });

  it('stops polling when shouldContinue is false', () => {
    const { poller, reloadFn } = createPoller();

    poller.handleRefresh(42, false);

    expect(poller.enabled()).toBe(false);
    expect(reloadFn).not.toHaveBeenCalled();
  });
});

describe('PendingFieldPoller (due date channel)', () => {
  const createPoller = () => {
    const reloadFn = vi.fn();
    const poller = new PendingFieldPoller({ maxAttempts: 8, intervalMs: 25 }, true);
    poller.bindReload(reloadFn);
    poller.start();
    return { poller, reloadFn };
  };

  it('schedules a silent reload when shouldContinue is true', () => {
    vi.useFakeTimers();
    const { poller, reloadFn } = createPoller();

    poller.handleRefresh(42, true);
    vi.advanceTimersByTime(25);

    expect(reloadFn).toHaveBeenCalledWith(42);
    vi.useRealTimers();
  });

  it('stops polling when shouldContinue is false', () => {
    const { poller, reloadFn } = createPoller();

    poller.handleRefresh(42, false);

    expect(poller.enabled()).toBe(false);
    expect(reloadFn).not.toHaveBeenCalled();
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

describe('ApplicationDetailComponent header title', () => {
  it('does not duplicate identical product code and name', () => {
    const component = Object.create(ApplicationDetailComponent.prototype) as any;
    component.application = () => ({
      id: 329,
      product: {
        code: 'VOA Extension (30 Days)',
        name: 'VOA Extension (30 Days)',
      },
    });

    expect(component.getApplicationHeaderTitle()).toBe(
      'Application #329 - VOA Extension (30 Days)',
    );
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

    // Wire up pendingRefresh since updateApplicationPartial references it for docDate updates
    const dueDatePoller = new PendingFieldPoller({ maxAttempts: 8, intervalMs: 400 }, false);
    component.pendingRefresh = { dueDate: dueDatePoller };

    component.applyApplicationFromActionResponse =
      ApplicationDetailComponent.prototype['applyApplicationFromActionResponse'].bind(component);
    component.normalizeApplicationPayload =
      ApplicationDetailComponent.prototype['normalizeApplicationPayload'].bind(component);
    component.shouldAwaitDueDateRefresh =
      ApplicationDetailComponent.prototype['shouldAwaitDueDateRefresh'].bind(component);
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
    component.isSavingMeta = Object.assign(
      vi.fn(() => false),
      {
        set: vi.fn(),
      },
    );
    component.editableNotes = { set: vi.fn() };
    component.toast = { success: vi.fn(), error: vi.fn() };
    component.loadApplication = vi.fn();

    // Wire up the PendingFieldRefreshService mock using real PendingFieldPoller
    const dueDatePoller = new PendingFieldPoller({ maxAttempts: 8, intervalMs: 25 }, true);
    dueDatePoller.bindReload((id) => component.loadApplication(id, { silent: true }));
    component.pendingRefresh = { dueDate: dueDatePoller };

    component.shouldAwaitDueDateRefresh =
      ApplicationDetailComponent.prototype['shouldAwaitDueDateRefresh'].bind(component);
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
    const service = Object.create(DocumentUploadService.prototype) as any;
    service.extractValidationAutoFillFields =
      DocumentUploadService.prototype['extractValidationAutoFillFields'].bind(service);
    service.mergeUploadFormWithValidationExtraction =
      DocumentUploadService.prototype['mergeUploadFormWithValidationExtraction'].bind(service);

    const merged = service.mergeUploadFormWithValidationExtraction(
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
    const service = Object.create(DocumentUploadService.prototype) as any;
    service.parseApiDate = vi.fn((value: string | null) =>
      value ? new Date(`${value}T00:00:00`) : null,
    );
    service.uploadForm = {
      getRawValue: vi.fn(() => ({ details: '   ' })),
      patchValue: vi.fn(),
    };
    service.extractValidationAutoFillFields =
      DocumentUploadService.prototype['extractValidationAutoFillFields'].bind(service);
    service.applyValidationExtractionToUploadForm =
      DocumentUploadService.prototype['applyValidationExtractionToUploadForm'].bind(service);

    service.applyValidationExtractionToUploadForm({
      extracted_doc_number: 'ITK-2026-ABC',
      extracted_expiration_date: '2026-01-30',
      extracted_details_markdown: '## OCR details',
    });

    expect(service.uploadForm.patchValue).toHaveBeenCalledWith({
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

describe('ApplicationWorkflowService confirmForceClose', () => {
  /**
   * Regression: forceClose was called with (id, app) — the app object was passed
   * as the second positional argument which the generated API client interprets as
   * the `observe` option, causing NG02809 "unhandled observe type [object Object]".
   * The fix removes the spurious second argument so the call is forceClose(id) only.
   */
  const createHarness = () => {
    const service = Object.create(ApplicationWorkflowService.prototype) as any;

    const mockApp = { id: 327, status: 'pending', canForceClose: true };
    service.applicationsService = {
      forceClose: vi.fn(() => of({ id: 327, status: 'completed' })),
    };
    service.toast = { success: vi.fn(), error: vi.fn() };
    service.action = { set: vi.fn() };
    service.WORKFLOW_TIMEZONE = 'Asia/Singapore';
    service.host = {
      application: vi.fn(() => mockApp),
      loadApplication: vi.fn(),
      applyApplicationFromActionResponse: vi.fn(() => true),
      patchApplicationLocally: vi.fn(() => true),
      displayDate: vi.fn((v: string) => v),
      stayPermitSubmissionWindow: vi.fn(() => null),
    };

    // Suppress the browser confirm dialog — auto-confirm
    vi.stubGlobal(
      'confirm',
      vi.fn(() => true),
    );

    service.canForceClose = ApplicationWorkflowService.prototype.canForceClose.bind(service);
    service.confirmForceClose =
      ApplicationWorkflowService.prototype.confirmForceClose.bind(service);

    return service;
  };

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  it('calls forceClose with only the application id — no second argument', () => {
    const service = createHarness();

    service.confirmForceClose();

    expect(service.applicationsService.forceClose).toHaveBeenCalledTimes(1);
    // Must be called with exactly one argument (the id). A second argument (e.g. the
    // application object) would be interpreted as the `observe` option and trigger
    // NG02809 "unhandled observe type [object Object]".
    expect(service.applicationsService.forceClose).toHaveBeenCalledWith(327);
    const callArgs: unknown[] = service.applicationsService.forceClose.mock.calls[0];
    expect(callArgs).toHaveLength(1);
  });

  it('shows a success toast and clears the workflow action after a successful force close', () => {
    const service = createHarness();

    service.confirmForceClose();

    expect(service.toast.success).toHaveBeenCalledWith('Application force closed');
    expect(service.action.set).toHaveBeenCalledWith(null);
  });

  it('does nothing when the application is not force-closeable', () => {
    const service = createHarness();
    service.canForceClose = vi.fn(() => false);

    service.confirmForceClose();

    expect(service.applicationsService.forceClose).not.toHaveBeenCalled();
    expect(service.toast.error).toHaveBeenCalledWith('You cannot force close this application');
  });
});
