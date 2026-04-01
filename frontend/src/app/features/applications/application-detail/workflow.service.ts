import { computed, inject, Injectable, signal, type Signal } from '@angular/core';

import {
  ApplicationsService,
  type ApplicationDetail,
  type ApplicationWorkflow,
} from '@/core/services/applications.service';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  formatDateForApi,
  getTodayInTimezoneDate,
  parseIsoDate,
} from '@/shared/utils/date-parsing';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

// ─── Public types ────────────────────────────────────────────────

export interface TimelineWorkflowItem {
  workflow: ApplicationWorkflow;
  gapDaysFromPrevious: number | null;
}

export interface PendingStartNotice {
  step: number;
  taskName: string;
  startDateDisplay: string;
  dueDateDisplay: string | null;
  expirationDateDisplay: string;
  windowDays: number;
}

/**
 * Callbacks the parent component provides so the service can read / mutate
 * shared state it does not own.
 */
export interface WorkflowServiceHost {
  /** The parent's `application` signal (read-only from the service's perspective). */
  application: Signal<ApplicationDetail | null>;
  /** Reload the application from the backend. */
  loadApplication(id: number): void;
  /** Apply a full application payload from an action response. Returns true on success. */
  applyApplicationFromActionResponse(response: unknown): boolean;
  /** Mutate the local application signal. Returns true on success. */
  patchApplicationLocally(mutator: (current: ApplicationDetail) => ApplicationDetail): boolean;
  /** Locale-aware date formatter for display strings. */
  displayDate(value: unknown): string;
  /** The computed stay-permit submission window for the pending-start notice. */
  stayPermitSubmissionWindow: Signal<{ firstDateIso: string; lastDateDisplay: string } | null>;
}

/**
 * Encapsulates all workflow lifecycle state and logic.
 * Provided at component level — each ApplicationDetailComponent gets its own instance.
 *
 * Follows the same pattern as {@link ApplicationCategorizationHandler} and
 * {@link ApplicationOcrService}.
 */
@Injectable()
export class ApplicationWorkflowService {
  private readonly applicationsService = inject(ApplicationsService);
  private readonly toast = inject(GlobalToastService);

  private host!: WorkflowServiceHost;
  private readonly WORKFLOW_TIMEZONE = 'Asia/Singapore';

  // ─── Public state ──────────────────────────────────────────────

  readonly action = signal<string | null>(null);

  readonly sortedWorkflows = computed(() => {
    const workflows = this.host?.application()?.workflows ?? [];
    return [...workflows].sort((a, b) => (a.task?.step ?? 0) - (b.task?.step ?? 0));
  });

  readonly timelineItems = computed<TimelineWorkflowItem[]>(() => {
    const workflows = this.sortedWorkflows();
    return workflows.map((workflow, index) => ({
      workflow,
      gapDaysFromPrevious: index > 0 ? this.calculateGapDays(workflows[index - 1], workflow) : null,
    }));
  });

  readonly hasWorkflowTasks = computed(() => {
    const app = this.host?.application();
    if (!app) return false;
    return this.sortedWorkflows().length > 0 || !!app.nextTask || !!app.hasNextTask;
  });

  readonly stepOneWorkflow = computed(
    () => this.sortedWorkflows().find((w) => w.task?.step === 1) ?? null,
  );

  readonly isApplicationDateLocked = computed(() => this.stepOneWorkflow()?.status === 'completed');

  readonly isDueDateLocked = computed(() => this.hasWorkflowTasks());

  readonly canReopen = computed(() => !!this.host?.application()?.isApplicationCompleted);

  readonly pendingStartNotice = computed<PendingStartNotice | null>(() => {
    const app = this.host?.application();
    const window = this.host?.stayPermitSubmissionWindow();
    if (!app || !window) return null;

    const todayIso = formatDateForApi(new Date());
    const today = parseIsoDate(todayIso);
    if (!today) return null;

    const firstWorkflow = this.sortedWorkflows()[0] ?? null;
    const scheduledStart =
      parseIsoDate(firstWorkflow?.startDate) ?? parseIsoDate(window.firstDateIso);
    if (!scheduledStart || scheduledStart.getTime() <= today.getTime()) return null;

    const task = firstWorkflow?.task ?? app.nextTask;
    if (!task) return null;

    return {
      step: task.step,
      taskName: task.name,
      startDateDisplay: this.host.displayDate(window.firstDateIso),
      dueDateDisplay: firstWorkflow?.dueDate ? this.host.displayDate(firstWorkflow.dueDate) : null,
      expirationDateDisplay: window.lastDateDisplay,
      windowDays: Number(app.product?.applicationWindowDays ?? 0) || 0,
    };
  });

  // ─── Predicate functions (bound for template pass-through) ─────

  readonly canRollbackWorkflowFn = (workflow: ApplicationWorkflow): boolean =>
    this.canRollbackWorkflow(workflow);

  readonly isWorkflowDueDateEditableFn = (workflow: ApplicationWorkflow): boolean =>
    this.isWorkflowDueDateEditable(workflow);

  readonly isWorkflowEditableFn = (workflow: ApplicationWorkflow): boolean =>
    this.isWorkflowEditable(workflow);

  readonly getWorkflowStatusGuardMessageFn = (workflow: ApplicationWorkflow): string | null =>
    this.getWorkflowStatusGuardMessage(workflow);

  // ─── Init ──────────────────────────────────────────────────────

  init(host: WorkflowServiceHost): void {
    this.host = host;
  }

  // ─── Public actions ────────────────────────────────────────────

  advanceWorkflow(): void {
    const app = this.host.application();
    if (!app) return;

    this.action.set('advance');
    this.applicationsService.advanceWorkflow(app.id).subscribe({
      next: (response) => {
        const applied = this.host.applyApplicationFromActionResponse(response);
        if (!applied) {
          this.host.loadApplication(app.id);
        }
        this.toast.success('Workflow advanced');
        this.action.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to advance workflow');
        this.action.set(null);
      },
    });
  }

  updateWorkflowStatus(workflowId: number, status: string | null): void {
    const app = this.host.application();
    if (!app || !status) return;

    const workflow = this.sortedWorkflows().find((entry) => entry.id === workflowId);
    if (workflow && this.isWorkflowStatusChangeBlocked(workflow, status)) {
      this.toast.error(this.getWorkflowStatusBlockedMessage(workflow));
      return;
    }

    this.action.set(`status-${workflowId}`);
    this.applicationsService.updateWorkflowStatus(app.id, workflowId, status).subscribe({
      next: (response) => {
        const appliedApplication = this.host.applyApplicationFromActionResponse(response);
        const patched = this.patchWorkflowFromActionResponse(workflowId, response, { status });
        const shouldReload =
          !patched || (!appliedApplication && (status === 'completed' || status === 'rejected'));
        if (shouldReload) {
          this.host.loadApplication(app.id);
        }
        this.toast.success('Workflow status updated');
        this.action.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to update workflow status');
        this.action.set(null);
      },
    });
  }

  updateWorkflowDueDate(workflow: ApplicationWorkflow, value: Date | null): void {
    const app = this.host.application();
    if (!app || !value || !this.isWorkflowDueDateEditable(workflow)) return;

    const dueDate = formatDateForApi(value);
    this.action.set(`due-${workflow.id}`);
    this.applicationsService.updateWorkflowDueDate(app.id, workflow.id, dueDate).subscribe({
      next: (response) => {
        const patched = this.patchWorkflowFromActionResponse(workflow.id, response, {
          dueDate,
          syncApplicationDueDate: dueDate,
        });
        if (!patched) {
          this.host.loadApplication(app.id);
        }
        this.toast.success('Task due date updated');
        this.action.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to update task due date');
        this.action.set(null);
      },
    });
  }

  rollbackWorkflow(workflow: ApplicationWorkflow): void {
    const app = this.host.application();
    if (!app || !this.canRollbackWorkflow(workflow)) return;

    if (
      !confirm(
        `Rollback Step ${workflow.task.step}? This removes the current task and reopens the previous task.`,
      )
    ) {
      return;
    }

    this.action.set(`rollback-${workflow.id}`);
    this.applicationsService.rollbackWorkflow(app.id, workflow.id).subscribe({
      next: (response) => {
        const applied = this.host.applyApplicationFromActionResponse(response);
        if (!applied) {
          const patched = this.patchRollbackLocally(workflow.id);
          if (!patched) {
            this.host.loadApplication(app.id);
          }
        }
        this.toast.success('Current task rolled back');
        this.action.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to rollback current task');
        this.action.set(null);
      },
    });
  }

  reopenApplication(): void {
    const app = this.host.application();
    if (!app) return;

    this.action.set('reopen');
    this.applicationsService.reopenApplication(app.id).subscribe({
      next: () => {
        const patched = this.patchReopenLocally();
        if (!patched) {
          this.host.loadApplication(app.id);
        }
        this.toast.success('Application re-opened');
        this.action.set(null);
      },
      error: (error) => {
        this.toast.error(extractServerErrorMessage(error) || 'Failed to re-open application');
        this.action.set(null);
      },
    });
  }

  canForceClose(): boolean {
    const app = this.host.application();
    return !!(
      app &&
      (app as any).canForceClose &&
      app.status !== 'completed' &&
      app.status !== 'rejected' &&
      !app.isDocumentCollectionCompleted
    );
  }

  confirmForceClose(): void {
    const app = this.host.application();
    if (!app) return;
    if (!this.canForceClose()) {
      this.toast.error('You cannot force close this application');
      return;
    }

    if (confirm(`Force close application #${app.id}? This will mark it as completed.`)) {
      this.action.set('force-close');
      this.applicationsService.forceClose(app.id).subscribe({
        next: (response) => {
          const applied = this.host.applyApplicationFromActionResponse(response);
          if (!applied) {
            const patched = this.patchForceCloseLocally();
            if (!patched) {
              this.host.loadApplication(app.id);
            }
          }
          this.toast.success('Application force closed');
          this.action.set(null);
        },
        error: (error) => {
          this.toast.error(extractServerErrorMessage(error) || 'Failed to force close application');
          this.action.set(null);
        },
      });
    }
  }

  // ─── Public predicates ─────────────────────────────────────────

  isWorkflowEditable(workflow: ApplicationWorkflow): boolean {
    if (!this.host.application()) return false;
    if (workflow.status === 'completed' || workflow.status === 'rejected') return false;
    const currentWorkflow = this.sortedWorkflows().at(-1);
    return !!currentWorkflow && currentWorkflow.id === workflow.id;
  }

  isWorkflowDueDateEditable(workflow: ApplicationWorkflow): boolean {
    return this.isWorkflowEditable(workflow);
  }

  canRollbackWorkflow(workflow: ApplicationWorkflow): boolean {
    const app = this.host.application();
    if (!app || app.status === 'completed' || app.status === 'rejected') return false;
    if (workflow.task.step <= 1) return false;
    const currentWorkflow = this.sortedWorkflows().at(-1);
    return !!currentWorkflow && currentWorkflow.id === workflow.id;
  }

  getWorkflowStatusGuardMessage(workflow: ApplicationWorkflow): string | null {
    const isBlocked =
      this.isWorkflowStatusChangeBlocked(workflow, 'processing') ||
      this.isWorkflowStatusChangeBlocked(workflow, 'completed');
    if (!isBlocked) return null;

    const previousWorkflow = this.getPreviousWorkflow(workflow);
    if (!previousWorkflow?.dueDate) return null;

    const formattedDate = this.host.displayDate(previousWorkflow.dueDate);
    return `Processing/Completed available on or after ${formattedDate} (GMT+8).`;
  }

  // ─── Private helpers ───────────────────────────────────────────

  private extractWorkflowPatchFromResponse(response: unknown): Partial<ApplicationWorkflow> {
    if (!response || typeof response !== 'object') {
      return {};
    }
    const raw = response as Record<string, unknown>;
    const patch: Partial<ApplicationWorkflow> = {};
    const status = raw['status'];
    const dueDate = raw['dueDate'];
    const completionDate = raw['completionDate'];
    const startDate = raw['startDate'];
    const isCurrentStep = raw['isCurrentStep'];
    const isOverdue = raw['isOverdue'];
    const hasNotes = raw['hasNotes'];

    if (typeof status === 'string' && status.trim()) {
      patch.status = status;
    }
    if (typeof dueDate === 'string' && dueDate.trim()) {
      patch.dueDate = dueDate;
    }
    if (typeof completionDate === 'string') {
      patch.completionDate = completionDate;
    } else if (completionDate === null) {
      patch.completionDate = null;
    }
    if (typeof startDate === 'string' && startDate.trim()) {
      patch.startDate = startDate;
    }
    if (typeof isCurrentStep === 'boolean') {
      patch.isCurrentStep = isCurrentStep;
    }
    if (typeof isOverdue === 'boolean') {
      patch.isOverdue = isOverdue;
    }
    if (typeof hasNotes === 'boolean') {
      patch.hasNotes = hasNotes;
    }

    return patch;
  }

  private patchWorkflowFromActionResponse(
    workflowId: number,
    response: unknown,
    options?: {
      status?: string;
      dueDate?: string;
      syncApplicationDueDate?: string;
    },
  ): boolean {
    const responsePatch = this.extractWorkflowPatchFromResponse(response);
    const statusFallback = options?.status;
    const dueDateFallback = options?.dueDate;
    let didPatch = false;

    this.host.patchApplicationLocally((current) => {
      const workflows = current.workflows ?? [];
      const index = workflows.findIndex((item) => item.id === workflowId);
      if (index < 0) return current;
      didPatch = true;

      const nextWorkflows = [...workflows];
      const existing = nextWorkflows[index]!;
      nextWorkflows[index] = {
        ...existing,
        ...responsePatch,
        ...(statusFallback ? { status: statusFallback } : {}),
        ...(dueDateFallback ? { dueDate: dueDateFallback } : {}),
      };

      return {
        ...current,
        workflows: nextWorkflows,
        ...(options?.syncApplicationDueDate ? { dueDate: options.syncApplicationDueDate } : {}),
      };
    });
    return didPatch;
  }

  private patchRollbackLocally(removedWorkflowId: number): boolean {
    return this.host.patchApplicationLocally((current) => {
      const workflows = current.workflows ?? [];
      const removing = workflows.find((item) => item.id === removedWorkflowId);
      if (!removing) return current;

      const nextWorkflows = workflows.filter((item) => item.id !== removedWorkflowId);
      let previousIndex = -1;
      let previousStep = Number.NEGATIVE_INFINITY;
      for (let i = 0; i < nextWorkflows.length; i += 1) {
        const step = nextWorkflows[i]?.task?.step ?? Number.NEGATIVE_INFINITY;
        if (step < removing.task.step && step >= previousStep) {
          previousStep = step;
          previousIndex = i;
        }
      }
      if (previousIndex >= 0) {
        const previous = nextWorkflows[previousIndex]!;
        nextWorkflows[previousIndex] = {
          ...previous,
          status: 'pending',
          isCurrentStep: true,
        };
      }

      const nextDueDate =
        previousIndex >= 0 ? nextWorkflows[previousIndex]?.dueDate : current.dueDate;
      return {
        ...current,
        workflows: nextWorkflows,
        dueDate: nextDueDate ?? current.dueDate ?? null,
      };
    });
  }

  private patchReopenLocally(): boolean {
    return this.host.patchApplicationLocally((current) => {
      const workflows = [...(current.workflows ?? [])];
      let lastIndex = -1;
      let lastStep = Number.NEGATIVE_INFINITY;
      for (let i = 0; i < workflows.length; i += 1) {
        const step = workflows[i]?.task?.step ?? Number.NEGATIVE_INFINITY;
        if (step >= lastStep) {
          lastStep = step;
          lastIndex = i;
        }
      }
      if (lastIndex >= 0) {
        const last = workflows[lastIndex]!;
        if (last.status === 'completed') {
          workflows[lastIndex] = { ...last, status: 'processing' };
        }
      }

      return {
        ...current,
        status: 'processing',
        isApplicationCompleted: false,
        workflows,
      };
    });
  }

  private patchForceCloseLocally(): boolean {
    return this.host.patchApplicationLocally((current) => ({
      ...current,
      status: 'completed',
      isApplicationCompleted: true,
    }));
  }

  private calculateGapDays(
    previous: ApplicationWorkflow,
    current: ApplicationWorkflow,
  ): number | null {
    const previousEnd = parseIsoDate(previous.completionDate);
    const currentStart = parseIsoDate(current.startDate);
    if (!previousEnd || !currentStart) return null;
    const msInDay = 24 * 60 * 60 * 1000;
    const diff = Math.round((currentStart.getTime() - previousEnd.getTime()) / msInDay);
    return Math.max(0, diff);
  }

  private getPreviousWorkflow(workflow: ApplicationWorkflow): ApplicationWorkflow | null {
    const workflows = this.sortedWorkflows();
    const index = workflows.findIndex((item) => item.id === workflow.id);
    if (index <= 0) return null;
    return workflows[index - 1] ?? null;
  }

  private isWorkflowStatusChangeBlocked(
    workflow: ApplicationWorkflow,
    nextStatus: string,
  ): boolean {
    if (nextStatus === 'rejected') return false;
    if (workflow.status !== 'pending') return false;
    if (nextStatus !== 'processing' && nextStatus !== 'completed') return false;

    const previousWorkflow = this.getPreviousWorkflow(workflow);
    const previousDueDate = parseIsoDate(previousWorkflow?.dueDate);
    if (!previousDueDate) return false;

    const today = getTodayInTimezoneDate(this.WORKFLOW_TIMEZONE);
    return previousDueDate.getTime() > today.getTime();
  }

  private getWorkflowStatusBlockedMessage(workflow: ApplicationWorkflow): string {
    const previousWorkflow = this.getPreviousWorkflow(workflow);
    if (!previousWorkflow?.dueDate) {
      return 'Status can be updated to Rejected only until previous step due date is reached.';
    }
    const formattedDate = this.host.displayDate(previousWorkflow.dueDate);
    return `You can set Processing/Completed only on or after ${formattedDate} (GMT+8).`;
  }
}
