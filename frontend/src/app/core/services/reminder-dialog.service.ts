import { Injectable, computed, signal } from '@angular/core';

import type { ReminderInboxItem } from '@/core/services/reminder-inbox.service';
import type { PushPayload } from '@/core/services/push-notifications.service';

export interface ReminderDialogItem {
  id: string;
  title: string;
  body: string;
  reminderId: string;
  timezone: string;
  scheduledFor: string;
  receivedAt: string;
  closing: boolean;
}

@Injectable({
  providedIn: 'root',
})
export class ReminderDialogService {
  private readonly _items = signal<ReminderDialogItem[]>([]);
  private readonly autoCloseTimers = new Map<string, ReturnType<typeof setTimeout>>();
  private sequence = 0;

  readonly items = this._items.asReadonly();
  readonly hasItems = computed(() => this._items().length > 0);

  enqueueFromPayload(payload: PushPayload): void {
    const data = payload.data ?? {};
    const title = String(payload.notification?.title || data['title'] || 'Daily Reminder').trim();
    const body = String(payload.notification?.body || data['body'] || 'You have a new reminder.').trim();
    const timezone = String(data['timezone'] || 'Asia/Makassar');
    const scheduledFor = String(data['scheduledFor'] || '');
    const reminderId = String(data['reminderId'] ?? '').trim();
    const receivedAt = new Date().toISOString();

    this.enqueue({
      title,
      body,
      timezone,
      scheduledFor,
      reminderId,
      receivedAt,
      autoCloseMs: 30000,
    });
  }

  enqueueFromInboxReminder(reminder: ReminderInboxItem): void {
    const reminderId = reminder.id > 0 ? String(reminder.id) : '';
    const scheduledFor = this.buildScheduledFor(reminder);
    const receivedAt = reminder.sentAt || new Date().toISOString();

    this.enqueue({
      title: 'Daily Reminder',
      body: reminder.content,
      timezone: reminder.timezone || 'Asia/Makassar',
      scheduledFor,
      reminderId,
      receivedAt,
    });
  }

  private enqueue(input: {
    title: string;
    body: string;
    timezone: string;
    scheduledFor: string;
    reminderId: string;
    receivedAt: string;
    autoCloseMs?: number;
  }): void {
    const { title, body, timezone, scheduledFor, reminderId, receivedAt, autoCloseMs } = input;

    if (!body) {
      return;
    }

    if (reminderId) {
      const duplicate = this._items().some((item) => item.reminderId === reminderId && !item.closing);
      if (duplicate) {
        return;
      }
    }

    const id = `${Date.now()}-${++this.sequence}`;
    const item: ReminderDialogItem = {
      id,
      title,
      body,
      reminderId,
      timezone,
      scheduledFor,
      receivedAt,
      closing: false,
    };

    this._items.update((items) => [item, ...items]);

    if (typeof autoCloseMs === 'number' && autoCloseMs > 0) {
      const timerId = setTimeout(() => this.close(id), autoCloseMs);
      this.autoCloseTimers.set(id, timerId);
    }
  }

  private buildScheduledFor(reminder: ReminderInboxItem): string {
    const date = (reminder.reminderDate || '').trim();
    const time = (reminder.reminderTime || '').trim();
    if (!date && !time) {
      return '';
    }
    const normalizedTime = time && time.length === 5 ? `${time}:00` : time;
    return `${date}T${normalizedTime}`.replace(/^T/, '');
  }

  close(id: string): void {
    if (!id) return;

    this.clearAutoCloseTimer(id);

    const nowClosing = this._items().some((item) => item.id === id && !item.closing);
    if (!nowClosing) {
      return;
    }

    this._items.update((items) =>
      items.map((item) => (item.id === id ? { ...item, closing: true } : item)),
    );

    setTimeout(() => {
      this.clearAutoCloseTimer(id);
      this._items.update((items) => items.filter((item) => item.id !== id));
    }, 520);
  }

  private clearAutoCloseTimer(id: string): void {
    const timer = this.autoCloseTimers.get(id);
    if (!timer) {
      return;
    }

    clearTimeout(timer);
    this.autoCloseTimers.delete(id);
  }
}
