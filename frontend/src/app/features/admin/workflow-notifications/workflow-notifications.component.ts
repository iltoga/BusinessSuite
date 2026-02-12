import { CommonModule } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { ChangeDetectionStrategy, Component, inject, signal, TemplateRef, ViewChild } from '@angular/core';
import { FormBuilder, ReactiveFormsModule, Validators } from '@angular/forms';
import { ZardButtonComponent } from '@/shared/components/button';
import { ZardComboboxComponent, type ZardComboboxOption } from '@/shared/components/combobox';
import { ZardDialogService } from '@/shared/components/dialog';
import { ZardInputDirective } from '@/shared/components/input';
import { GlobalToastService } from '@/core/services/toast.service';

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
  changeDetection: ChangeDetectionStrategy.OnPush,
})
export class WorkflowNotificationsComponent {
  @ViewChild('pushTestDialogTemplate', { static: true }) pushTestDialogTemplate!: TemplateRef<any>;

  private http = inject(HttpClient);
  private fb = inject(FormBuilder);
  private dialogService = inject(ZardDialogService);
  private toast = inject(GlobalToastService);
  readonly notifications = signal<any[]>([]);
  readonly loading = signal(false);
  readonly sendingPush = signal(false);
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

  constructor() {
    this.load();
  }

  load(): void {
    this.loading.set(true);
    this.http.get<any>('/api/workflow-notifications/').subscribe({
      next: (res) => {
        this.notifications.set(res?.results ?? res ?? []);
        this.loading.set(false);
      },
      error: () => this.loading.set(false),
    });
  }

  resend(id: number): void {
    this.http.post(`/api/workflow-notifications/${id}/resend/`, {}).subscribe({
      next: () => this.load(),
      error: () => this.toast.error('Failed to resend notification'),
    });
  }

  cancel(id: number): void {
    this.http.post(`/api/workflow-notifications/${id}/cancel/`, {}).subscribe({
      next: () => this.load(),
      error: () => this.toast.error('Failed to cancel notification'),
    });
  }

  remove(id: number): void {
    this.http.delete(`/api/workflow-notifications/${id}/`).subscribe({
      next: () => this.load(),
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
}
