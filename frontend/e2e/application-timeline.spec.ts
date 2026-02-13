import { expect, test, type Page } from '@playwright/test';

type WorkflowStatus = 'pending' | 'processing' | 'completed' | 'rejected';

interface WorkflowState {
  id: number;
  task: {
    id: number;
    name: string;
    step: number;
    duration: number;
    durationIsBusinessDays: boolean;
    notifyDaysBefore: number;
    lastStep: boolean;
  };
  startDate: string;
  dueDate: string;
  completionDate: string | null;
  status: WorkflowStatus;
  notes: string;
  isCurrentStep: boolean;
  isOverdue: boolean;
  isNotificationDateReached: boolean;
  hasNotes: boolean;
}

interface ApplicationState {
  id: number;
  customer: {
    id: number;
    fullName: string;
    email: string;
    whatsapp: string;
  };
  product: {
    id: number;
    name: string;
    productType: string;
  };
  docDate: string;
  dueDate: string;
  addDeadlinesToCalendar: boolean;
  notifyCustomer: boolean;
  notifyCustomerChannel: 'whatsapp' | 'email' | null;
  status: WorkflowStatus;
  notes: string;
  documents: any[];
  workflows: WorkflowState[];
  isDocumentCollectionCompleted: boolean;
  isApplicationCompleted: boolean;
  hasNextTask: boolean;
  nextTask: {
    id: number;
    name: string;
    step: number;
    duration: number;
    durationIsBusinessDays: boolean;
    notifyDaysBefore: number;
    lastStep: boolean;
  } | null;
  hasInvoice: boolean;
  canForceClose: boolean;
}

const APPLICATION_ID = 42;

function createWorkflow(step: number): WorkflowState {
  return {
    id: 100 + step,
    task: {
      id: 200 + step,
      name: `Task ${step}`,
      step,
      duration: 2,
      durationIsBusinessDays: false,
      notifyDaysBefore: 0,
      lastStep: step === 3,
    },
    startDate: `2026-02-0${step}`,
    dueDate: `2026-02-0${step + 1}`,
    completionDate: null,
    status: 'pending',
    notes: '',
    isCurrentStep: step === 1,
    isOverdue: false,
    isNotificationDateReached: false,
    hasNotes: false,
  };
}

function buildApplicationState(): ApplicationState {
  const step1 = createWorkflow(1);
  return {
    id: APPLICATION_ID,
    customer: {
      id: 501,
      fullName: 'Timeline Test Customer',
      email: 'timeline@example.com',
      whatsapp: '+628123456789',
    },
    product: {
      id: 601,
      name: 'Timeline Product',
      productType: 'visa',
    },
    docDate: '2026-02-01',
    dueDate: '2026-02-10',
    addDeadlinesToCalendar: true,
    notifyCustomer: false,
    notifyCustomerChannel: null,
    status: 'pending',
    notes: '',
    documents: [],
    workflows: [step1],
    isDocumentCollectionCompleted: false,
    isApplicationCompleted: false,
    hasNextTask: true,
    nextTask: step1.task,
    hasInvoice: false,
    canForceClose: true,
  };
}

function getTodayIsoDate(): string {
  return new Date().toISOString().slice(0, 10);
}

function updateCurrentMarkers(app: ApplicationState): void {
  const sorted = [...app.workflows].sort((a, b) => a.task.step - b.task.step);
  const current = sorted.at(-1);
  app.workflows = sorted.map((wf) => ({ ...wf, isCurrentStep: current?.id === wf.id }));
}

function recomputeApplicationStatus(app: ApplicationState): void {
  updateCurrentMarkers(app);
  const hasRejected = app.workflows.some((wf) => wf.status === 'rejected');
  const current = app.workflows.at(-1);

  if (hasRejected) {
    app.status = 'rejected';
    app.isApplicationCompleted = false;
  } else if (current && current.task.step === 3 && current.status === 'completed') {
    app.status = 'completed';
    app.isApplicationCompleted = true;
  } else if (app.workflows.some((wf) => wf.status === 'processing')) {
    app.status = 'processing';
    app.isApplicationCompleted = false;
  } else {
    app.status = 'pending';
    app.isApplicationCompleted = false;
  }

  app.canForceClose = app.status !== 'completed' && app.status !== 'rejected';
  const currentTask = app.workflows.at(-1)?.task ?? null;
  app.nextTask = currentTask;
  app.hasNextTask = Boolean(currentTask && app.status !== 'completed' && app.status !== 'rejected');
}

async function selectCurrentWorkflowStatus(page: Page, statusLabel: 'Completed' | 'Rejected') {
  const timelineCard = page.locator('z-card').filter({
    has: page.getByRole('heading', { name: 'Tasks Timeline' }),
  });

  await timelineCard.getByRole('button', { name: 'Select option' }).first().click();
  await page.getByRole('option', { name: new RegExp(statusLabel, 'i') }).first().click();
}

async function openApplicationDetailFromList(page: Page) {
  await page.goto('/applications');
  await expect(page.getByRole('heading', { name: 'Applications' })).toBeVisible();

  await page.getByLabel('Row actions').first().click();
  await page.locator('button').filter({ hasText: /^Manage$/ }).first().click();

  await expect(page).toHaveURL(/\/applications\/42$/);
  await expect(page.getByRole('heading', { name: 'Tasks Timeline' })).toBeVisible();
}

test.describe('Application task timeline workflow', () => {
  test.beforeEach(async ({ page }) => {
    await page.addInitScript(() => {
      try {
        localStorage.setItem(
          'auth_token',
          [
            'eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9',
            'eyJzdWIiOiJlMmUtdXNlciIsImV4cCI6NDEwMjQ0NDgwMCwiaXNfc3VwZXJ1c2VyIjp0cnVlLCJmdWxsX25hbWUiOiJFMkUgVXNlciJ9',
            'mock-signature',
          ].join('.'),
        );
        localStorage.setItem('auth_refresh_token', 'mock-refresh');
        (window as any).APP_CONFIG = { MOCK_AUTH_ENABLED: 'True' };
      } catch (e) {
        // ignore
      }
    });

    let application = buildApplicationState();

    await page.route('**/api/**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({}),
      }),
    );

    await page.route('**/api/app-config/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ MOCK_AUTH_ENABLED: 'True' }),
      }),
    );
    await page.route('**/api/app-config', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ MOCK_AUTH_ENABLED: 'True' }),
      }),
    );
    await page.route('**/api/mock-auth-config/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          sub: 'mock-user',
          email: 'mock@example.com',
          isSuperuser: true,
          roles: ['admin'],
        }),
      }),
    );
    await page.route('**/api/user-settings/me/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({ theme: 'zinc', dark_mode: false }),
      }),
    );
    await page.route(/\/api\/customer-applications\/(?:\?.*)?$/, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify({
          count: 1,
          next: null,
          previous: null,
          results: [
            {
              id: APPLICATION_ID,
              customer: application.customer,
              product: application.product,
              docDate: application.docDate,
              dueDate: application.dueDate,
              status: application.status,
              notes: application.notes,
              hasInvoice: application.hasInvoice,
              invoiceId: null,
              readyForInvoice: false,
              canForceClose: true,
              createdAt: '2026-02-01T10:00:00Z',
              updatedAt: '2026-02-01T10:00:00Z',
            },
          ],
        }),
      }),
    );

    await page.route(`**/api/customer-applications/${APPLICATION_ID}/`, (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(application),
      }),
    );

    await page.route(`**/api/customer-applications/${APPLICATION_ID}/workflows/*/status/`, async (route) => {
      const body = (route.request().postDataJSON() ?? {}) as { status?: WorkflowStatus };
      const nextStatus = body.status;
      const match = route.request().url().match(/workflows\/(\d+)\/status\/$/);
      const workflowId = match ? Number(match[1]) : NaN;

      const workflow = application.workflows.find((wf) => wf.id === workflowId);
      if (!workflow || !nextStatus) {
        await route.fulfill({ status: 404, contentType: 'application/json', body: JSON.stringify({}) });
        return;
      }

      if (
        (workflow.status === 'completed' || workflow.status === 'rejected') &&
        workflow.status !== nextStatus
      ) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Finalized tasks cannot be changed' }),
        });
        return;
      }

      const current = [...application.workflows].sort((a, b) => a.task.step - b.task.step).at(-1);
      if (current && current.id !== workflow.id && workflow.status !== nextStatus) {
        await route.fulfill({
          status: 400,
          contentType: 'application/json',
          body: JSON.stringify({ detail: 'Only the current task can be updated' }),
        });
        return;
      }

      workflow.status = nextStatus;
      if (nextStatus === 'completed' || nextStatus === 'rejected') {
        workflow.completionDate = getTodayIsoDate();
      }

      if (nextStatus === 'completed' && workflow.task.step < 3) {
        const nextStep = workflow.task.step + 1;
        const hasNext = application.workflows.some((wf) => wf.task.step === nextStep);
        if (!hasNext) {
          const nextWorkflow = createWorkflow(nextStep);
          nextWorkflow.startDate = getTodayIsoDate();
          application.workflows.push(nextWorkflow);
        }
      }

      recomputeApplicationStatus(application);

      await route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify(workflow),
      });
    });

    await page.route('**/api/document-types/**', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      }),
    );
    await page.route('**/api/document-types/', (route) =>
      route.fulfill({
        status: 200,
        contentType: 'application/json',
        body: JSON.stringify([]),
      }),
    );
  });

  test('completes 3-task timeline and closes application automatically', async ({ page }) => {
    await openApplicationDetailFromList(page);
    await expect(page.getByText('Step 1')).toBeVisible();

    await selectCurrentWorkflowStatus(page, 'Completed');
    await expect(page.getByText('Step 2')).toBeVisible();

    await selectCurrentWorkflowStatus(page, 'Completed');
    await expect(page.getByText('Step 3')).toBeVisible();

    await selectCurrentWorkflowStatus(page, 'Completed');

    await expect(page.getByText('Application Status')).toBeVisible();
    await expect(page.getByText('Completed').first()).toBeVisible();

    const timelineCard = page.locator('z-card').filter({
      has: page.getByRole('heading', { name: 'Tasks Timeline' }),
    });
    await expect(timelineCard.getByRole('button', { name: 'Select option' })).toHaveCount(0);
  });

  test('rejected task sets application to rejected and keeps invoice action available', async ({ page }) => {
    await openApplicationDetailFromList(page);

    await selectCurrentWorkflowStatus(page, 'Completed');
    await expect(page.getByText('Step 2')).toBeVisible();

    await selectCurrentWorkflowStatus(page, 'Rejected');

    await expect(page.getByText('Rejected').first()).toBeVisible();
    await expect(page.getByRole('button', { name: 'Create Invoice' })).toBeVisible();

    const timelineCard = page.locator('z-card').filter({
      has: page.getByRole('heading', { name: 'Tasks Timeline' }),
    });
    await expect(timelineCard.getByRole('button', { name: 'Select option' })).toHaveCount(0);
  });
});
