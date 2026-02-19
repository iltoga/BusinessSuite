import { CommonModule, isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import {
  ChangeDetectionStrategy,
  Component,
  PLATFORM_ID,
  DestroyRef,
  computed,
  inject,
  signal,
  TemplateRef,
  ViewChild,
} from '@angular/core';
import { takeUntilDestroyed } from '@angular/core/rxjs-interop';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';
import { GlobalToastService } from '@/core/services/toast.service';
import {
  WorkflowNotificationsStreamEvent,
  WorkflowNotificationsStreamService,
} from './workflow-notifications-stream.service';
import { Subscription, catchError, finalize, map, of, Subject, switchMap } from 'rxjs';

@Component({
  selector: 'app-workflow-notifications',
  standalone: true,
  imports: [
    CommonModule,
    ReactiveFormsModule,
    ZardButtonComponent,
    ZardComboboxComponent,
    ZardInputDirective,
  ],
  templateUrl: './workflow-notifications.component.html',
  styleUrls: ['./workflow-notifications.component.css'],
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkflowNotificationsComponent {
  @ViewChild('pushTestDialogTemplate', { static: true }) pushTestDialogTemplate!: TemplateRef<any>;
  @ViewChild('whatsappTestDialogTemplate', { static: true })
  whatsappTestDialogTemplate!: TemplateRef<any>;

  private http = inject(HttpClient);
  private fb = inject(FormBuilder);
  private destroyRef = inject(DestroyRef);
  private platformId = inject(PLATFORM_ID);
  private dialogService = inject(ZardDialogService);
  private toast = inject(GlobalToastService);
  private streamService = inject(WorkflowNotificationsStreamService);
  private readonly manualRefresh$ = new Subject<boolean>();
  private streamSubscription: Subscription | null = null;
  private reconnectTimeoutId: number | null = null;
  private reconnectAttempt = 0;
  private readonly reconnectBaseDelayMs = 2000;
  private readonly reconnectMaxDelayMs = 30000;
  readonly notifications = signal<any[]>([]);
  readonly lastUpdatedAt = signal<Date | null>(null);
  readonly loading = signal(false);
  readonly liveConnected = signal(false);
  readonly liveConnecting = signal(false);
  readonly liveStatusText = computed(() => {
    if (this.liveConnected()) {
      return 'Live updates connected';
    }
    if (this.liveConnecting()) {
      return 'Live updates connecting...';
    }
    return 'Live updates reconnecting...';
  });
  readonly liveDotOffline = computed(() => !this.liveConnected() && !this.liveConnecting());
  readonly sendingPush = signal(false);
  readonly sendingWhatsapp = signal(false);
  readonly resendingIds = signal<number[]>([]);
  readonly users = signal<any[]>([]);
  readonly userOptions = signal<ZardComboboxOption[]>([]);
  dialogRef: any = null;

  readonly pushTestForm = this.fb.group({
    userId: [null as string | null, Validators.required],
    title: ['Revis Bali CRM Notification', [Validators.required, Validators.maxLength(120)]],
    body: ['Push notification test completed.', [Validators.required, Validators.maxLength(500)]],
    link: ['/'],
    data: ['{}'],
  });

  readonly whatsappTestForm = this.fb.group({
    to: [''],
    subject: ['Revis Bali CRM WhatsApp Test', [Validators.required, Validators.maxLength(120)]],
    body: [
      'WhatsApp test message from Revis Bali CRM.',
      [Validators.required, Validators.maxLength(1000)],
    ],
  });

  constructor() {
    this.bindNotificationStream();
    this.load(false);
    if (isPlatformBrowser(this.platformId)) {
      this.connectLiveStream();
      this.destroyRef.onDestroy(() => this.teardownLiveStream());
    }
  }

  load(showError = true): void {
    this.manualRefresh$.next(showError);
  }

  private bindNotificationStream(): void {
    this.manualRefresh$
      .pipe(
        switchMap((showError) => {
          this.loading.set(true);
          return this.http.get<any>('/api/workflow-notifications/').pipe(
            map((res) => res?.results ?? res ?? []),
            catchError((error) => {
              if (showError) {
                const message = error?.error?.error || 'Failed to load notifications';
                this.toast.error(String(message));
              }
              return of(null);
            }),
            finalize(() => this.loading.set(false)),
          );
        }),
        takeUntilDestroyed(this.destroyRef),
      )
      .subscribe((items) => {
        if (items) {
          this.notifications.set(items);
          this.lastUpdatedAt.set(new Date());
        }
      });
  }

  private connectLiveStream(): void {
    this.clearReconnectTimeout();
    this.liveConnecting.set(true);
    this.liveConnected.set(false);
    this.streamSubscription?.unsubscribe();
    this.streamSubscription = this.streamService
      .connect()
      .pipe(takeUntilDestroyed(this.destroyRef))
      .subscribe({
        next: (event) => this.handleLiveEvent(event),
        error: () => {
          this.liveConnecting.set(false);
          this.liveConnected.set(false);
          this.scheduleReconnect();
        },
      });
  }

  private handleLiveEvent(event: WorkflowNotificationsStreamEvent): void {
    this.liveConnecting.set(false);
    this.liveConnected.set(event.event !== 'workflow_notifications_error');
    this.reconnectAttempt = 0;
    if (event.event === 'workflow_notifications_error') {
      this.liveConnected.set(false);
      this.scheduleReconnect();
      return;
    }
    if (event.event === 'workflow_notifications_changed') {
      this.load(false);
      return;
    }
    if (event.event === 'workflow_notifications_snapshot' && this.notifications().length === 0) {
      this.load(false);
    }
  }

  private scheduleReconnect(): void {
    if (!isPlatformBrowser(this.platformId)) {
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

  resend(id: number): void {
    if (this.isResending(id)) {
      return;
    }

    this.setResending(id, true);
    this.http.post<any>(`/api/workflow-notifications/${id}/resend/`, {}).subscribe({
      next: (response) => {
        this.setResending(id, false);
        const status = String(response?.status || 'updated');
        const reference = String(response?.external_reference || '').trim();
        this.toast.success(
          reference ? `Notification resent (${status}) [${reference}]` : `Notification resent (${status})`,
        );
        this.load(false);
      },
      error: (error) => {
        this.setResending(id, false);
        const message = error?.error?.error || 'Failed to resend notification';
        this.toast.error(String(message));
      },
    });
  }

  cancel(id: number): void {
    this.http.post(`/api/workflow-notifications/${id}/cancel/`, {}).subscribe({
      next: () => this.load(false),
      error: () => this.toast.error('Failed to cancel notification'),
    });
  }

  remove(id: number): void {
    this.http.delete(`/api/workflow-notifications/${id}/`).subscribe({
      next: () => this.load(false),
      error: () => this.toast.error('Failed to delete notification'),
    });
  }

  openPushTestDialog(): void {
    this.pushTestForm.reset({
      userId: null,
      title: 'Revis Bali CRM Notification',
      body: 'Push notification test completed.',
      link: '/',
      data: '{}',
    });
    this.loadUsersForPushDialog();
    this.dialogRef = this.dialogService.create({
      zTitle: 'Send Test Push Notification',
      zContent: this.pushTestDialogTemplate,
      zHideFooter: true,
      zClosable: true,
      zWidth: '760px',
      zCustomClasses: 'border-2 border-primary/30 sm:max-w-[760px]',
      zOnCancel: () => {
        this.dialogRef = null;
      },
    });
  }

  openWhatsappTestDialog(): void {
    this.whatsappTestForm.reset({
      to: '',
      subject: 'Revis Bali CRM WhatsApp Test',
      body: 'WhatsApp test message from Revis Bali CRM.',
    });
    this.dialogRef = this.dialogService.create({
      zTitle: 'Send Test WhatsApp',
      zContent: this.whatsappTestDialogTemplate,
      zHideFooter: true,
      zClosable: true,
      zWidth: '760px',
      zCustomClasses: 'border-2 border-primary/30 sm:max-w-[760px]',
      zOnCancel: () => {
        this.dialogRef = null;
      },
    });
  }

  private loadUsersForPushDialog(): void {
    this.http.get<any[]>('/api/push-notifications/users/').subscribe({
      next: (res) => {
        const list = Array.isArray(res) ? res : [];
        const normalized = list.map((user) => {
          const activeCount = Number(
            user.active_push_subscriptions ?? user.activePushSubscriptions ?? 0,
          );
          return {
            ...user,
            activePushSubscriptions: activeCount,
          };
        });
        this.users.set(normalized);
        this.userOptions.set(
          normalized.map((user) => ({
            value: String(user.id),
            label: `${user.full_name || user.fullName || user.username} (${user.email || user.username}) - ${user.activePushSubscriptions} active device${user.activePushSubscriptions === 1 ? '' : 's'}`,
          })),
        );
      },
      error: () => {
        this.users.set([]);
        this.userOptions.set([]);
        this.toast.error('Failed to load users');
      },
    });
  }

  selectedUserActiveSubscriptions(): number {
    const selectedUserId = Number(this.pushTestForm.get('userId')?.value);
    if (!selectedUserId) return 0;
    const selectedUser = this.users().find((user) => Number(user.id) === selectedUserId);
    return Number(selectedUser?.activePushSubscriptions || 0);
  }

  sendTestPush(): void {
    if (this.pushTestForm.invalid || this.sendingPush()) {
      this.pushTestForm.markAllAsTouched();
      return;
    }

    const raw = this.pushTestForm.getRawValue();
    const selectedUserId = Number(raw.userId);
    const selectedUser = this.users().find((user) => Number(user.id) === selectedUserId);
    const activeSubscriptions = Number(selectedUser?.activePushSubscriptions || 0);
    if (!selectedUser) {
      this.toast.error('Selected user not found');
      return;
    }
    if (activeSubscriptions === 0) {
      this.toast.error(
        'Selected user has no active push subscriptions. Open CRM in browser, allow notifications, then retry.',
      );
      return;
    }

    let dataPayload: Record<string, unknown> = {};
    try {
      dataPayload = raw.data?.trim() ? JSON.parse(raw.data) : {};
      if (typeof dataPayload !== 'object' || dataPayload === null || Array.isArray(dataPayload)) {
        throw new Error('Data payload must be a JSON object');
      }
    } catch {
      this.pushTestForm.get('data')?.setErrors({ invalidJson: true });
      return;
    }

    const payload = {
      user_id: selectedUserId,
      title: raw.title?.trim() || 'Revis Bali CRM Notification',
      body: raw.body?.trim() || 'Push notification test completed.',
      link: raw.link?.trim() || '/',
      data: dataPayload,
    };

    this.sendingPush.set(true);
    this.http.post<any>('/api/push-notifications/send-test/', payload).subscribe({
      next: (response) => {
        this.sendingPush.set(false);
        const sent = Number(response?.sent || 0);
        const failed = Number(response?.failed || 0);
        const skipped = Number(response?.skipped || 0);
        if (sent < 1) {
          this.toast.error(
            `Push was not delivered (sent=${sent}, failed=${failed}, skipped=${skipped}). Check device registration and FCM config.`,
          );
          return;
        }
        this.toast.success('Test push notification sent');
        this.dialogRef?.close();
        this.dialogRef = null;
      },
      error: (error) => {
        this.sendingPush.set(false);
        const message = error?.error?.error || 'Failed to send test push notification';
        this.toast.error(String(message));
      },
    });
  }

  sendTestWhatsapp(): void {
    if (this.whatsappTestForm.invalid || this.sendingWhatsapp()) {
      this.whatsappTestForm.markAllAsTouched();
      return;
    }

    const raw = this.whatsappTestForm.getRawValue();
    const payload = {
      to: raw.to?.trim() || '',
      subject: raw.subject?.trim() || 'Revis Bali CRM WhatsApp Test',
      body: raw.body?.trim() || 'WhatsApp test message from Revis Bali CRM.',
    };

    this.sendingWhatsapp.set(true);
    this.http.post<any>('/api/push-notifications/send-test-whatsapp/', payload).subscribe({
      next: (response) => {
        this.sendingWhatsapp.set(false);
        const recipient = response?.recipient || payload.to || 'default test number';
        this.toast.success(`Test WhatsApp sent to ${recipient}`);
        this.dialogRef?.close();
        this.dialogRef = null;
        this.load(false);
      },
      error: (error) => {
        this.sendingWhatsapp.set(false);
        const message = error?.error?.error || 'Failed to send test WhatsApp';
        this.toast.error(String(message));
      },
    });
  }

  isResending(id: number): boolean {
    return this.resendingIds().includes(id);
  }

  private setResending(id: number, value: boolean): void {
    const current = this.resendingIds();
    if (value) {
      if (current.includes(id)) {
        return;
      }
      this.resendingIds.set([...current, id]);
      return;
    }
    this.resendingIds.set(current.filter((itemId) => itemId !== id));
  }
}
