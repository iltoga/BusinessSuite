import { CommonModule, isPlatformBrowser } from '@angular/common';
import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  TemplateRef,
  computed,
  inject,
  signal,
  viewChild,
  type OnDestroy,
  type OnInit,
} from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ActivatedRoute, ParamMap } from '@angular/router';
import { Subscription, catchError, finalize, of } from 'rxjs';

import { AuthService } from '@/core/services/auth.service';
import { GlobalToastService } from '@/core/services/toast.service';
import { ZardBadgeComponent } from '@/shared/components/badge';
import { ZardButtonComponent } from '@/shared/components/button';
import {
  ColumnConfig,
  ColumnFilterChangeEvent,
  DataTableAction,
  DataTableComponent,
  SortEvent,
} from '@/shared/components/data-table/data-table.component';
import { ZardDateInputComponent } from '@/shared/components/date-input';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';
import { PaginationControlsComponent } from '@/shared/components/pagination-controls';
import { SearchToolbarComponent } from '@/shared/components/search-toolbar';
import { ZardTooltipImports } from '@/shared/components/tooltip';
import {
  TypeaheadComboboxComponent,
  TypeaheadOption,
} from '@/shared/components/typeahead-combobox';
import { AppDatePipe } from '@/shared/pipes/app-date-pipe';
import { extractServerErrorMessage } from '@/shared/utils/form-errors';

import { RemindersStreamEvent, RemindersStreamService } from './reminders-stream.service';
import {
  ReminderBulkWritePayload,
  ReminderItem,
  ReminderStatus,
  ReminderUserOption,
  ReminderWritePayload,
  RemindersService,
} from './reminders.service';

const DEFAULT_TIMEZONE = 'Asia/Makassar';

@Component({
  selector: 'app-reminders',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardButtonComponent,
    DataTableComponent,
    PaginationControlsComponent,
    SearchToolbarComponent,
    ZardBadgeComponent,
    ZardInputDirective,
    ZardDateInputComponent,
    TypeaheadComboboxComponent,
    ...ZardTooltipImports,
    AppDatePipe,
  ],
  templateUrl: './reminders.component.html',
  styleUrls: ['./reminders.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class RemindersComponent implements OnInit, OnDestroy {
  private readonly fb = inject(FormBuilder);
  private readonly remindersService = inject(RemindersService);
  private readonly remindersStreamService = inject(RemindersStreamService);
  private readonly authService = inject(AuthService);
  private readonly route = inject(ActivatedRoute);
  private readonly toast = inject(GlobalToastService);
  private readonly dialogService = inject(ZardDialogService);
  private readonly platformId = inject(PLATFORM_ID);

  private readonly isBrowser = isPlatformBrowser(this.platformId);

  private readonly dataTable = viewChild.required(DataTableComponent);
  private readonly statusTemplate =
    viewChild.required<TemplateRef<{ $implicit: ReminderItem; value: any; row: ReminderItem }>>(
      'statusTemplate',
    );
  private readonly scheduleTemplate =
    viewChild.required<TemplateRef<{ $implicit: ReminderItem; value: any; row: ReminderItem }>>(
      'scheduleTemplate',
    );
  private readonly recipientTemplate =
    viewChild.required<TemplateRef<{ $implicit: ReminderItem; value: any; row: ReminderItem }>>(
      'recipientTemplate',
    );
  private readonly contentTemplate =
    viewChild.required<TemplateRef<{ $implicit: ReminderItem; value: any; row: ReminderItem }>>(
      'contentTemplate',
    );
  private readonly deliveryChannelTemplate =
    viewChild.required<TemplateRef<{ $implicit: ReminderItem; value: any; row: ReminderItem }>>(
      'deliveryChannelTemplate',
    );
  private readonly reminderDialogTemplate =
    viewChild.required<TemplateRef<unknown>>('reminderDialogTemplate');

  private dialogRef: any = null;
  private streamSubscription: Subscription | null = null;
  private routeSubscription: Subscription | null = null;
  private reconnectTimeoutId: number | null = null;
  private reconnectAttempt = 0;

  private readonly reconnectBaseDelayMs = 2000;
  private readonly reconnectMaxDelayMs = 30000;

  readonly reminders = signal<ReminderItem[]>([]);
  readonly isLoading = signal(false);
  readonly isSaving = signal(false);
  readonly isDialogOpen = signal(false);

  readonly query = signal('');
  readonly page = signal(1);
  readonly pageSize = signal(10);
  readonly totalItems = signal(0);
  readonly ordering = signal<string | undefined>(undefined);
  readonly statusFilter = signal<ReminderStatus[]>(['pending']);
  readonly createdFrom = signal<Date>(this.todayDate());
  readonly createdTo = signal<Date>(this.todayDate());

  readonly editingReminder = signal<ReminderItem | null>(null);
  readonly liveConnected = signal(false);
  readonly liveConnecting = signal(false);

  readonly totalPages = computed(() => {
    const total = this.totalItems();
    const size = this.pageSize();
    return Math.max(1, Math.ceil(total / size));
  });

  readonly liveStatusText = computed(() => {
    if (this.liveConnected()) {
      return 'Live updates connected';
    }
    if (this.liveConnecting()) {
      return 'Live updates connecting...';
    }
    return 'Live updates reconnecting...';
  });

  readonly statusFilterOptions = [
    { value: 'pending', label: 'Pending' },
    { value: 'sent', label: 'Sent' },
    { value: 'failed', label: 'Failed' },
  ] as const;

  readonly columns = computed<ColumnConfig<ReminderItem>[]>(() => [
    {
      key: 'status',
      header: 'Status',
      sortable: true,
      sortKey: 'status_rank',
      template: this.statusTemplate(),
      filter: {
        options: this.statusFilterOptions,
        selectedValues: this.statusFilter(),
        emptyLabel: 'No status found',
        searchPlaceholder: 'Filter status...',
      },
    },
    {
      key: 'scheduledFor',
      header: 'Reminder Date/Time',
      sortable: true,
      sortKey: 'scheduled_for',
      template: this.scheduleTemplate(),
    },
    {
      key: 'userFullName',
      header: 'Recipient',
      template: this.recipientTemplate(),
    },
    {
      key: 'content',
      header: 'Content',
      template: this.contentTemplate(),
    },
    {
      key: 'deliveryChannel',
      header: 'Delivery',
      template: this.deliveryChannelTemplate(),
    },
    {
      key: 'actions',
      header: 'Actions',
    },
  ]);

  readonly actions = computed<DataTableAction<ReminderItem>[]>(() => [
    {
      label: 'Edit',
      icon: 'settings',
      variant: 'warning',
      action: (item) => this.openEditDialog(item),
    },
    {
      label: 'Delete',
      icon: 'trash',
      variant: 'destructive',
      isDestructive: true,
      action: (item) => this.deleteReminder(item),
    },
  ]);

  readonly reminderForm = this.fb.nonNullable.group({
    reminderDate: [new Date(), Validators.required],
    reminderTime: [this.defaultTime(), Validators.required],
    timezone: [DEFAULT_TIMEZONE, Validators.required],
    userIds: [[] as string[]],
    content: ['', [Validators.required, Validators.maxLength(2000)]],
  });

  readonly usersLoader = (query?: string, page = 1) =>
    this.remindersService.listUsers(query ?? '', page, 20);

  readonly timezoneLoader = (query?: string, page = 1) =>
    this.remindersService.listTimezones(query ?? '', page, 50);

  readonly userMap = (user: ReminderUserOption): TypeaheadOption => {
    const name = user.fullName || user.username;
    const emailOrUsername = user.email || user.username;
    const deviceLabel = `${user.activePushSubscriptions} active device${user.activePushSubscriptions === 1 ? '' : 's'}`;

    return {
      value: String(user.id),
      label: `${name} (${emailOrUsername})`,
      display: `${name} (${emailOrUsername})`,
      description: deviceLabel,
      search: `${name} ${emailOrUsername} ${user.username}`.trim(),
    };
  };

  readonly timezoneMap = (item: { value: string; label: string }): TypeaheadOption => ({
    value: item.value,
    label: item.label,
    display: item.label,
    search: item.label,
  });

  ngOnInit(): void {
    this.routeSubscription = this.route.queryParamMap.subscribe((queryParams) => {
      this.applyQueryFilters(queryParams);
      this.page.set(1);
      this.loadReminders();
    });

    if (this.isBrowser) {
      this.connectLiveStream();
    }
  }

  ngOnDestroy(): void {
    this.routeSubscription?.unsubscribe();
    this.routeSubscription = null;
    this.closeDialog();
    this.teardownLiveStream();
  }

  onQueryChange(value: string): void {
    const next = value.trim();
    if (this.query() === next) return;
    this.query.set(next);
    this.page.set(1);
    this.loadReminders();
  }

  onPageChange(page: number): void {
    this.page.set(page);
    this.loadReminders();
  }

  onSortChange(sort: SortEvent): void {
    const ordering = sort.direction === 'desc' ? `-${sort.column}` : sort.column;
    this.ordering.set(ordering);
    this.page.set(1);
    this.loadReminders();
  }

  onColumnFilterChange(event: ColumnFilterChangeEvent): void {
    if (event.column !== 'status') {
      return;
    }

    const normalized = event.values.filter(
      (value): value is ReminderStatus =>
        value === 'pending' || value === 'sent' || value === 'failed',
    );

    this.statusFilter.set(normalized);
    this.page.set(1);
    this.loadReminders();
  }

  onCreatedFromChange(value: Date | null | undefined): void {
    const normalized = this.normalizeDateOnly(value ?? this.todayDate());
    if (this.sameDate(this.createdFrom(), normalized)) {
      return;
    }

    this.createdFrom.set(normalized);
    this.page.set(1);
    this.loadReminders();
  }

  onCreatedToChange(value: Date | null | undefined): void {
    const normalized = this.normalizeDateOnly(value ?? this.todayDate());
    if (this.sameDate(this.createdTo(), normalized)) {
      return;
    }

    this.createdTo.set(normalized);
    this.page.set(1);
    this.loadReminders();
  }

  onEnterSearch(): void {
    this.dataTable().focusFirstRowIfNone();
  }

  refresh(): void {
    this.loadReminders(false);
  }

  openCreateDialog(): void {
    this.editingReminder.set(null);
    this.reminderForm.reset({
      reminderDate: new Date(),
      reminderTime: this.defaultTime(),
      timezone: DEFAULT_TIMEZONE,
      userIds: [],
      content: '',
    });

    this.openDialog('Add Reminder');
    this.prefillLoggedInUserRecipient();
  }

  openEditDialog(reminder: ReminderItem): void {
    this.editingReminder.set(reminder);
    this.reminderForm.reset({
      reminderDate: this.parseIsoDate(reminder.reminderDate),
      reminderTime: this.normalizeTime(reminder.reminderTime),
      timezone: reminder.timezone || DEFAULT_TIMEZONE,
      userIds: [String(reminder.user)],
      content: reminder.content,
    });

    this.openDialog('Edit Reminder');
  }

  closeDialog(): void {
    this.dialogRef?.close();
    this.dialogRef = null;
    this.isDialogOpen.set(false);
    this.editingReminder.set(null);
  }

  saveReminder(): void {
    if (this.isSaving()) {
      return;
    }

    if (this.reminderForm.invalid) {
      this.reminderForm.markAllAsTouched();
      return;
    }

    const formValue = this.reminderForm.getRawValue();
    const reminderDateIso = this.toIsoDate(formValue.reminderDate);
    const reminderTime = this.normalizeTime(formValue.reminderTime);

    if (!reminderDateIso || !reminderTime) {
      this.toast.error('Reminder date and time are required.');
      return;
    }

    const selectedUserIds = this.parseUserIds(formValue.userIds);
    const payload: ReminderWritePayload = {
      reminderDate: reminderDateIso,
      reminderTime,
      timezone: formValue.timezone?.trim() || DEFAULT_TIMEZONE,
      content: formValue.content.trim(),
    };

    if (!payload.content) {
      this.toast.error('Reminder content cannot be empty.');
      return;
    }

    const editing = this.editingReminder();
    this.isSaving.set(true);

    if (editing) {
      if (selectedUserIds.length > 1) {
        this.toast.error('Editing supports one recipient only.');
        this.isSaving.set(false);
        return;
      }

      if (selectedUserIds.length === 1) {
        payload.userId = selectedUserIds[0];
      }

      this.remindersService
        .update(editing.id, payload)
        .pipe(
          catchError((error) => {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message ? `Failed to update reminder: ${message}` : 'Failed to update reminder',
            );
            return of(null);
          }),
          finalize(() => this.isSaving.set(false)),
        )
        .subscribe((updated) => {
          if (!updated) return;
          this.toast.success('Reminder updated');
          this.closeDialog();
          this.loadReminders(false);
        });
      return;
    }

    if (selectedUserIds.length > 1) {
      const bulkPayload: ReminderBulkWritePayload = {
        reminderDate: payload.reminderDate,
        reminderTime: payload.reminderTime,
        timezone: payload.timezone,
        content: payload.content,
        userIds: selectedUserIds,
      };

      this.remindersService
        .bulkCreate(bulkPayload)
        .pipe(
          catchError((error) => {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message ? `Failed to add reminders: ${message}` : 'Failed to add reminders',
            );
            return of(null);
          }),
          finalize(() => this.isSaving.set(false)),
        )
        .subscribe((created) => {
          if (!created) return;
          this.toast.success(`Created ${created.length} reminders`);
          this.closeDialog();
          this.loadReminders(false);
        });
      return;
    }

    if (selectedUserIds.length === 1) {
      payload.userId = selectedUserIds[0];
    }

    this.remindersService
      .create(payload)
      .pipe(
        catchError((error) => {
          const message = extractServerErrorMessage(error);
          this.toast.error(
            message ? `Failed to add reminder: ${message}` : 'Failed to add reminder',
          );
          return of(null);
        }),
        finalize(() => this.isSaving.set(false)),
      )
      .subscribe((created) => {
        if (!created) return;
        this.toast.success('Reminder added');
        this.closeDialog();
        this.loadReminders(false);
      });
  }

  deleteReminder(reminder: ReminderItem): void {
    const message = `Delete reminder for ${reminder.userFullName || 'this user'}?`;
    if (!confirm(message)) {
      return;
    }

    this.remindersService
      .delete(reminder.id)
      .pipe(
        catchError((error) => {
          const messageText = extractServerErrorMessage(error);
          this.toast.error(
            messageText ? `Failed to delete reminder: ${messageText}` : 'Failed to delete reminder',
          );
          return of(null);
        }),
      )
      .subscribe((result) => {
        if (result === null) return;
        this.toast.success('Reminder deleted');
        this.loadReminders(false);
      });
  }

  statusVariant(
    status: ReminderStatus,
  ): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
    switch (status) {
      case 'sent':
        return 'success';
      case 'failed':
        return 'destructive';
      case 'pending':
      default:
        return 'secondary';
    }
  }

  deliveryChannelLabel(channel: string): string {
    switch (channel) {
      case 'in_app':
        return 'In-App';
      case 'system':
        return 'System';
      default:
        return '—';
    }
  }

  deliveryChannelVariant(
    channel: string,
  ): 'default' | 'secondary' | 'success' | 'warning' | 'destructive' {
    switch (channel) {
      case 'in_app':
        return 'default';
      case 'system':
        return 'warning';
      default:
        return 'secondary';
    }
  }

  displayReminderTime(value: string): string {
    return this.normalizeTime(value) || '--:--';
  }

  onStatusBadgeClick(event: MouseEvent, row: ReminderItem): void {
    if (row.status !== 'failed' || !row.errorMessage?.trim()) {
      return;
    }

    event.preventDefault();
    event.stopPropagation();

    void this.copyToClipboard(row.errorMessage.trim()).then((copied) => {
      if (copied) {
        this.toast.success('Failure error copied to clipboard.');
      } else {
        this.toast.error('Could not copy error to clipboard.');
      }
    });
  }

  private loadReminders(showError = true): void {
    this.isLoading.set(true);
    this.remindersService
      .list({
        page: this.page(),
        pageSize: this.pageSize(),
        search: this.query() || undefined,
        ordering: this.ordering(),
        statuses: this.statusFilter(),
        createdFrom: this.toIsoDate(this.createdFrom()),
        createdTo: this.toIsoDate(this.createdTo()),
      })
      .pipe(
        catchError((error) => {
          if (showError) {
            const message = extractServerErrorMessage(error);
            this.toast.error(
              message ? `Failed to load reminders: ${message}` : 'Failed to load reminders',
            );
          }
          return of({ count: 0, next: null, previous: null, results: [] as ReminderItem[] });
        }),
        finalize(() => this.isLoading.set(false)),
      )
      .subscribe((response) => {
        this.totalItems.set(response.count);

        const maxPage = Math.max(1, Math.ceil(response.count / this.pageSize()));
        if (this.page() > maxPage) {
          this.page.set(maxPage);
          this.loadReminders(false);
          return;
        }

        this.reminders.set(response.results);
      });
  }

  private openDialog(title: string): void {
    this.isDialogOpen.set(true);
    this.dialogRef = this.dialogService.create({
      zTitle: title,
      zContent: this.reminderDialogTemplate(),
      zHideFooter: true,
      zClosable: true,
      zWidth: '820px',
      zCustomClasses: 'border-2 border-primary/30 sm:max-w-[820px]',
      zOnCancel: () => {
        this.dialogRef = null;
        this.isDialogOpen.set(false);
        this.editingReminder.set(null);
      },
    });
  }

  private connectLiveStream(): void {
    this.clearReconnectTimeout();
    this.liveConnecting.set(true);
    this.liveConnected.set(false);
    this.streamSubscription?.unsubscribe();
    this.streamSubscription = this.remindersStreamService.connect().subscribe({
      next: (event) => this.handleLiveEvent(event),
      error: () => {
        this.liveConnecting.set(false);
        this.liveConnected.set(false);
        this.scheduleReconnect();
      },
    });
  }

  private handleLiveEvent(event: RemindersStreamEvent): void {
    this.liveConnecting.set(false);
    this.liveConnected.set(event.event !== 'calendar_reminders_error');
    this.reconnectAttempt = 0;

    if (event.event === 'calendar_reminders_error') {
      this.liveConnected.set(false);
      this.scheduleReconnect();
      return;
    }

    if (event.event === 'calendar_reminders_changed') {
      this.loadReminders(false);
      return;
    }

    if (event.event === 'calendar_reminders_snapshot' && this.reminders().length === 0) {
      this.loadReminders(false);
    }
  }

  private scheduleReconnect(): void {
    if (!this.isBrowser) {
      return;
    }

    this.clearReconnectTimeout();
    const delay = Math.min(
      this.reconnectMaxDelayMs,
      this.reconnectBaseDelayMs * 2 ** this.reconnectAttempt,
    );
    this.reconnectAttempt += 1;
    this.reconnectTimeoutId = window.setTimeout(() => this.connectLiveStream(), delay);
  }

  private clearReconnectTimeout(): void {
    if (this.reconnectTimeoutId !== null) {
      window.clearTimeout(this.reconnectTimeoutId);
      this.reconnectTimeoutId = null;
    }
  }

  private teardownLiveStream(): void {
    this.clearReconnectTimeout();
    this.streamSubscription?.unsubscribe();
    this.streamSubscription = null;
  }

  private prefillLoggedInUserRecipient(): void {
    const currentSelection = this.reminderForm.controls.userIds.value ?? [];
    if (currentSelection.length > 0) {
      return;
    }

    const claims = this.authService.claims();
    const email = (claims?.email ?? '').trim();
    const username = (claims?.sub ?? '').trim();
    const fullName = (claims?.fullName ?? '').trim();
    const query = email || username || fullName;

    if (!query) {
      return;
    }

    this.remindersService.listUsers(query, 1, 20).subscribe({
      next: (users) => {
        const normalizedEmail = email.toLowerCase();
        const normalizedUsername = username.toLowerCase();

        const exactByEmail = normalizedEmail
          ? users.find((user) => user.email.toLowerCase() === normalizedEmail)
          : undefined;
        const exactByUsername = normalizedUsername
          ? users.find((user) => user.username.toLowerCase() === normalizedUsername)
          : undefined;
        const exact = exactByEmail || exactByUsername;

        if (exact) {
          this.reminderForm.controls.userIds.setValue([String(exact.id)]);
          return;
        }

        if (users.length === 1) {
          this.reminderForm.controls.userIds.setValue([String(users[0].id)]);
        }
      },
    });
  }

  private parseUserIds(raw: string[] | null | undefined): number[] {
    const result: number[] = [];
    for (const value of raw ?? []) {
      const numeric = Number(value);
      if (!Number.isInteger(numeric) || numeric <= 0) continue;
      if (!result.includes(numeric)) {
        result.push(numeric);
      }
    }
    return result;
  }

  private defaultTime(): string {
    const now = new Date();
    const hour = String(now.getHours()).padStart(2, '0');
    const minute = String(now.getMinutes()).padStart(2, '0');
    return `${hour}:${minute}`;
  }

  private normalizeTime(value: string): string {
    if (!value) return '';
    const trimmed = String(value).trim();
    const match = trimmed.match(/^(\d{1,2}):(\d{2})(?::\d{2})?$/);
    if (!match) return '';

    const hour = Number(match[1]);
    const minute = Number(match[2]);
    if (hour < 0 || hour > 23 || minute < 0 || minute > 59) return '';

    return `${String(hour).padStart(2, '0')}:${String(minute).padStart(2, '0')}`;
  }

  private toIsoDate(date: Date): string {
    if (!(date instanceof Date) || Number.isNaN(date.getTime())) {
      return '';
    }

    const year = date.getFullYear();
    const month = String(date.getMonth() + 1).padStart(2, '0');
    const day = String(date.getDate()).padStart(2, '0');
    return `${year}-${month}-${day}`;
  }

  private async copyToClipboard(text: string): Promise<boolean> {
    if (!this.isBrowser || !text) {
      return false;
    }

    try {
      if (navigator.clipboard?.writeText) {
        await navigator.clipboard.writeText(text);
        return true;
      }
    } catch {
      // fallback below
    }

    try {
      const textarea = document.createElement('textarea');
      textarea.value = text;
      textarea.setAttribute('readonly', '');
      textarea.style.position = 'fixed';
      textarea.style.top = '-1000px';
      textarea.style.left = '-1000px';
      document.body.appendChild(textarea);
      textarea.focus();
      textarea.select();
      const copied = document.execCommand('copy');
      document.body.removeChild(textarea);
      return copied;
    } catch {
      return false;
    }
  }

  private applyQueryFilters(queryParams: ParamMap): void {
    const parsedStatuses = this.parseStatuses(
      queryParams.get('statuses') ?? queryParams.get('status'),
    );
    this.statusFilter.set(parsedStatuses ?? ['pending']);

    const today = this.todayDate();
    const createdFrom =
      this.parseQueryDate(
        queryParams.get('createdFrom') ??
          queryParams.get('created_from') ??
          queryParams.get('dateFrom') ??
          queryParams.get('date_from'),
      ) ?? today;
    const createdTo =
      this.parseQueryDate(
        queryParams.get('createdTo') ??
          queryParams.get('created_to') ??
          queryParams.get('dateTo') ??
          queryParams.get('date_to'),
      ) ?? today;

    this.createdFrom.set(createdFrom);
    this.createdTo.set(createdTo);
  }

  private parseStatuses(raw: string | null): ReminderStatus[] | null {
    if (!raw) {
      return null;
    }

    const values = raw
      .split(',')
      .map((value) => value.trim().toLowerCase())
      .filter(
        (value): value is ReminderStatus =>
          value === 'pending' || value === 'sent' || value === 'failed',
      );

    return values.length > 0 ? values : ['pending'];
  }

  private parseQueryDate(raw: string | null): Date | null {
    const match = String(raw ?? '')
      .trim()
      .match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) {
      return null;
    }

    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    if (!Number.isInteger(year) || !Number.isInteger(month) || !Number.isInteger(day)) {
      return null;
    }

    return this.normalizeDateOnly(new Date(year, month - 1, day));
  }

  private normalizeDateOnly(date: Date): Date {
    return new Date(date.getFullYear(), date.getMonth(), date.getDate());
  }

  private sameDate(left: Date, right: Date): boolean {
    return (
      left.getFullYear() === right.getFullYear() &&
      left.getMonth() === right.getMonth() &&
      left.getDate() === right.getDate()
    );
  }

  private todayDate(): Date {
    return this.normalizeDateOnly(new Date());
  }

  private parseIsoDate(value: string): Date {
    const match = String(value || '').match(/^(\d{4})-(\d{2})-(\d{2})$/);
    if (!match) {
      return new Date();
    }

    const year = Number(match[1]);
    const month = Number(match[2]);
    const day = Number(match[3]);
    return new Date(year, month - 1, day);
  }
}
