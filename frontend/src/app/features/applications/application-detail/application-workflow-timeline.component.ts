import { CommonModule } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  EventEmitter,
  Input,
  OnChanges,
  Output,
} from '@angular/core';
import { FormsModule } from '@angular/forms';

import type { ApplicationWorkflow } from '@/core/services/applications.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardCardComponent } from '@/shared/components/card';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';

interface TimelineWorkflowItem {
  workflow: ApplicationWorkflow;
  gapDaysFromPrevious: number | null;
}

interface PendingStartNotice {
  step: number;
  taskName: string;
  startDateDisplay: string;
  dueDateDisplay: string | null;
  expirationDateDisplay: string;
  windowDays: number;
}

interface DocumentCollectionStatus {
  label:
    | 'Document Collection Pending'
    | 'Document Collection Incomplete'
    | 'Document Collection Complete';
  type: 'default' | 'secondary' | 'warning' | 'success' | 'destructive';
}

@Component({
  selector: 'app-application-workflow-timeline',
  standalone: true,
  imports: [
    CommonModule,
    FormsModule,
    ZardCardComponent,
    ZardButtonComponent,
    ZardBadgeComponent,
    ZardDateInputComponent,
    ZardComboboxComponent,
    AppDatePipe,
  ],
  templateUrl: './application-workflow-timeline.component.html',
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class ApplicationWorkflowTimelineComponent implements OnChanges {
  private readonly workflowTimezone = 'Asia/Singapore';

  private readonly workflowDueDateCache = new Map<number, Date | null>();
  private readonly workflowStatusOptionsCache = new Map<number, ZardComboboxOption[]>();
  private readonly workflowCanRollbackCache = new Map<number, boolean>();
  private readonly workflowDueDateEditableCache = new Map<number, boolean>();
  private readonly workflowEditableCache = new Map<number, boolean>();
  private readonly workflowStatusGuardMessageCache = new Map<number, string | null>();

  @Input({ required: true }) canReopen = false;
  @Input({ required: true }) workflowAction: string | null = null;
  @Input({ required: true }) sortedWorkflowsCount = 0;
  @Input({ required: true }) timelineItems: TimelineWorkflowItem[] = [];
  @Input({ required: true }) documentCollectionStatus!: DocumentCollectionStatus;
  @Input() pendingStartNotice: PendingStartNotice | null = null;

  @Input({ required: true }) canRollbackWorkflow!: (workflow: ApplicationWorkflow) => boolean;
  @Input({ required: true }) isWorkflowDueDateEditable!: (workflow: ApplicationWorkflow) => boolean;
  @Input({ required: true }) isWorkflowEditable!: (workflow: ApplicationWorkflow) => boolean;
  @Input({ required: true }) getWorkflowStatusGuardMessage!: (
    workflow: ApplicationWorkflow,
  ) => string | null;

  @Output() readonly reopenApplication = new EventEmitter<void>();
  @Output() readonly rollbackWorkflow = new EventEmitter<ApplicationWorkflow>();
  @Output() readonly updateWorkflowDueDate = new EventEmitter<{
    workflow: ApplicationWorkflow;
    value: Date | null;
  }>();
  @Output() readonly updateWorkflowStatus = new EventEmitter<{
    workflowId: number;
    status: string | null;
  }>();

  ngOnChanges(): void {
    this.rebuildWorkflowCaches();
  }

  shouldDisablePendingWorkflow(workflow: ApplicationWorkflow): boolean {
    if (workflow.status !== 'pending') {
      return false;
    }
    const startDate = this.parseIsoDate(workflow.startDate);
    if (!startDate) {
      return false;
    }
    const today = this.getTodayInWorkflowTimezoneDate();
    return startDate.getTime() > today.getTime();
  }

  getWorkflowStatusVariant(
    status: string,
    isOverdue?: boolean,
  ): 'default' | 'secondary' | 'warning' | 'success' | 'destructive' {
    if (isOverdue && status !== 'completed' && status !== 'rejected') {
      return 'destructive';
    }
    switch (status) {
      case 'completed':
        return 'success';
      case 'processing':
        return 'warning';
      case 'rejected':
        return 'destructive';
      case 'pending':
      default:
        return 'secondary';
    }
  }

  getWorkflowDotClass(status: string): string {
    switch (status) {
      case 'completed':
        return 'timeline-dot-completed';
      case 'rejected':
        return 'timeline-dot-rejected';
      case 'processing':
        return 'timeline-dot-processing';
      case 'pending':
      default:
        return 'timeline-dot-pending';
    }
  }

  getWorkflowDueDateAsDate(workflow: ApplicationWorkflow): Date | null {
    return this.workflowDueDateCache.get(workflow.id) ?? null;
  }

  getWorkflowStatusOptions(workflow: ApplicationWorkflow): ZardComboboxOption[] {
    return this.workflowStatusOptionsCache.get(workflow.id) ?? [];
  }

  canRollback(workflow: ApplicationWorkflow): boolean {
    return this.workflowCanRollbackCache.get(workflow.id) ?? false;
  }

  isDueDateEditable(workflow: ApplicationWorkflow): boolean {
    return this.workflowDueDateEditableCache.get(workflow.id) ?? false;
  }

  isEditable(workflow: ApplicationWorkflow): boolean {
    return this.workflowEditableCache.get(workflow.id) ?? false;
  }

  workflowStatusGuardMessage(workflow: ApplicationWorkflow): string | null {
    return this.workflowStatusGuardMessageCache.get(workflow.id) ?? null;
  }

  getTimelineGapLabel(days: number | null): string {
    if (days === null) {
      return '';
    }
    if (days <= 0) {
      return 'Started same day';
    }
    if (days === 1) {
      return 'Started after 1 day';
    }
    return `Started after ${days} days`;
  }

  private getPreviousWorkflow(workflow: ApplicationWorkflow): ApplicationWorkflow | null {
    const workflows = this.timelineItems.map((item) => item.workflow);
    const index = workflows.findIndex((item) => item.id === workflow.id);
    if (index <= 0) {
      return null;
    }
    return workflows[index - 1] ?? null;
  }

  private isWorkflowStatusChangeBlocked(
    workflow: ApplicationWorkflow,
    nextStatus: string,
  ): boolean {
    if (nextStatus === 'rejected') {
      return false;
    }
    if (workflow.status !== 'pending') {
      return false;
    }
    if (nextStatus !== 'processing' && nextStatus !== 'completed') {
      return false;
    }

    const previousWorkflow = this.getPreviousWorkflow(workflow);
    const previousDueDate = this.parseIsoDate(previousWorkflow?.dueDate);
    if (!previousDueDate) {
      return false;
    }

    const today = this.getTodayInWorkflowTimezoneDate();
    return previousDueDate.getTime() > today.getTime();
  }

  private getTodayInWorkflowTimezoneDate(): Date {
    const parts = new Intl.DateTimeFormat('en-US', {
      timeZone: this.workflowTimezone,
      year: 'numeric',
      month: '2-digit',
      day: '2-digit',
    }).formatToParts(new Date());
    const year = Number(parts.find((part) => part.type === 'year')?.value);
    const month = Number(parts.find((part) => part.type === 'month')?.value);
    const day = Number(parts.find((part) => part.type === 'day')?.value);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return new Date();
    }
    return new Date(Date.UTC(year, month - 1, day));
  }

  private parseIsoDate(value?: string | null): Date | null {
    if (!value) {
      return null;
    }
    const parts = value.split('-');
    if (parts.length !== 3) {
      return null;
    }
    const year = Number(parts[0]);
    const month = Number(parts[1]);
    const day = Number(parts[2]);
    if (!Number.isFinite(year) || !Number.isFinite(month) || !Number.isFinite(day)) {
      return null;
    }
    return new Date(Date.UTC(year, month - 1, day));
  }

  private parseApiDate(value: unknown): Date | null {
    if (value instanceof Date && !Number.isNaN(value.getTime())) {
      return new Date(value.getFullYear(), value.getMonth(), value.getDate());
    }
    if (typeof value !== 'string') {
      return null;
    }
    const trimmed = value.trim();
    if (!trimmed) {
      return null;
    }
    const match = trimmed.match(/^(\d{4})-(\d{1,2})-(\d{1,2})$/);
    if (!match) {
      const parsed = new Date(trimmed);
      if (Number.isNaN(parsed.getTime())) {
        return null;
      }
      return new Date(parsed.getFullYear(), parsed.getMonth(), parsed.getDate());
    }
    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    const date = new Date(year, month - 1, day);
    if (date.getFullYear() !== year || date.getMonth() !== month - 1 || date.getDate() !== day) {
      return null;
    }
    return date;
  }

  private rebuildWorkflowCaches(): void {
    this.workflowDueDateCache.clear();
    this.workflowStatusOptionsCache.clear();
    this.workflowCanRollbackCache.clear();
    this.workflowDueDateEditableCache.clear();
    this.workflowEditableCache.clear();
    this.workflowStatusGuardMessageCache.clear();

    for (const item of this.timelineItems) {
      const workflow = item.workflow;
      this.workflowDueDateCache.set(workflow.id, this.parseApiDate(workflow.dueDate));
      this.workflowStatusOptionsCache.set(workflow.id, this.buildWorkflowStatusOptions(workflow));
      this.workflowCanRollbackCache.set(workflow.id, this.canRollbackWorkflow(workflow));
      this.workflowDueDateEditableCache.set(workflow.id, this.isWorkflowDueDateEditable(workflow));
      this.workflowEditableCache.set(workflow.id, this.isWorkflowEditable(workflow));
      this.workflowStatusGuardMessageCache.set(
        workflow.id,
        this.getWorkflowStatusGuardMessage(workflow),
      );
    }
  }

  private buildWorkflowStatusOptions(workflow: ApplicationWorkflow): ZardComboboxOption[] {
    const options: ZardComboboxOption[] = [
      { value: 'pending', label: 'Pending' },
      { value: 'processing', label: 'Processing' },
      { value: 'completed', label: 'Completed' },
      { value: 'rejected', label: 'Rejected' },
    ];

    return options.map((option) => ({
      ...option,
      disabled:
        option.value !== workflow.status &&
        this.isWorkflowStatusChangeBlocked(workflow, option.value),
    }));
  }
}
