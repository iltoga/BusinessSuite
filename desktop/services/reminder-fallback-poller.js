'use strict';

const DEFAULT_INTERVAL_MS = 60_000;
const MAX_BACKOFF_MS = 5 * 60_000;
const MAX_SEEN_REMINDERS = 4_000;
const MAX_SEEN_AGE_MS = 24 * 60 * 60 * 1_000;

class ReminderFallbackPoller {
  constructor({
    baseUrl,
    intervalMs = DEFAULT_INTERVAL_MS,
    onReminder,
    onUnreadCount,
    request,
    log,
  } = {}) {
    this.baseUrl = this.normalizeOrigin(baseUrl);
    this.intervalMs = Math.max(15_000, Number(intervalMs) || DEFAULT_INTERVAL_MS);
    this.onReminder = typeof onReminder === 'function' ? onReminder : null;
    this.onUnreadCount = typeof onUnreadCount === 'function' ? onUnreadCount : null;
    this.request =
      typeof request === 'function'
        ? request
        : (...args) => {
            if (typeof fetch !== 'function') {
              throw new Error('No fetch implementation available for reminder fallback poller.');
            }
            return fetch(...args);
          };
    this.log = typeof log === 'function' ? log : () => {};

    this.authToken = null;
    this.timer = null;
    this.running = false;
    this.failureCount = 0;
    this.seenReminderIds = new Map();
  }

  setBaseUrl(baseUrl) {
    this.baseUrl = this.normalizeOrigin(baseUrl);
  }

  setAuthToken(token) {
    const normalized = typeof token === 'string' && token.trim() ? token.trim() : null;
    const changed = this.authToken !== normalized;
    this.authToken = normalized;

    if (!this.running) {
      this.start();
      return;
    }

    if (changed) {
      this.failureCount = 0;
    }

    this.scheduleNext(0);
  }

  markReminderSeen(rawReminderId) {
    const reminderId = this.toPositiveInt(rawReminderId);
    if (!reminderId) {
      return;
    }

    this.seenReminderIds.set(reminderId, Date.now());
    this.pruneSeenReminderIds();
  }

  start() {
    if (this.running) {
      return;
    }

    this.running = true;
    this.failureCount = 0;
    this.scheduleNext(0);
  }

  stop({ resetSeen = false } = {}) {
    this.running = false;
    this.failureCount = 0;
    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    if (resetSeen) {
      this.seenReminderIds.clear();
    }
  }

  destroy() {
    this.stop({ resetSeen: true });
  }

  scheduleNext(delayMs) {
    if (!this.running) {
      return;
    }

    if (this.timer) {
      clearTimeout(this.timer);
      this.timer = null;
    }

    const timeoutMs = Math.max(0, Number(delayMs) || 0);
    this.timer = setTimeout(() => {
      void this.runCycle();
    }, timeoutMs);
  }

  async runCycle() {
    if (!this.running) {
      return;
    }

    if (!this.baseUrl) {
      this.log('debug', 'Reminder poll cycle skipped: baseUrl is not configured.');
      this.scheduleNext(this.intervalMs);
      return;
    }

    this.log(
      'debug',
      `Reminder poll cycle start. base_url=${this.baseUrl} auth_mode=${this.authToken ? 'bearer' : 'session'}`,
    );
    try {
      await this.pollNow();
      this.failureCount = 0;
      this.log('debug', `Reminder poll cycle success. next_in_ms=${this.intervalMs}`);
      this.scheduleNext(this.intervalMs);
    } catch (error) {
      this.failureCount += 1;
      const backoff = Math.min(this.intervalMs * 2 ** Math.min(this.failureCount, 4), MAX_BACKOFF_MS);
      this.log('warn', `Reminder poll failed. retry_in_ms=${backoff} error=${String(error)}`);
      this.scheduleNext(backoff);
    }
  }

  async pollNow() {
    const headers = {
      Accept: 'application/json',
    };
    if (this.authToken) {
      headers.Authorization = `Bearer ${this.authToken}`;
    }

    const response = await this.request(`${this.baseUrl}/api/calendar-reminders/inbox/?limit=100`, {
      method: 'GET',
      headers,
    });
    this.log('debug', `Reminder poll HTTP response. status=${response.status}`);

    if (response.status === 401 || response.status === 403) {
      if (this.onUnreadCount) {
        this.onUnreadCount(0);
      }
      if (this.authToken) {
        this.log(
          'warn',
          `Reminder poll unauthorized with bearer token (status=${response.status}). Waiting for refreshed auth.`,
        );
      }
      return;
    }

    if (!response.ok) {
      const body = await response.text();
      throw new Error(`HTTP ${response.status}: ${body.slice(0, 300)}`);
    }

    const payload = await response.json();
    const unreadCount = this.toNonNegativeInt(payload?.unreadCount ?? payload?.unread_count);
    const reminders = Array.isArray(payload?.today) ? payload.today : [];
    this.log(
      'debug',
      `Reminder poll payload parsed. unread_count=${unreadCount} reminders_today=${reminders.length}`,
    );
    if (this.onUnreadCount) {
      this.onUnreadCount(unreadCount);
    }

    for (const rawReminder of reminders) {
      const reminder = this.normalizeReminder(rawReminder);
      if (!reminder) {
        this.log('debug', 'Reminder poll skipped item: invalid reminder payload.');
        continue;
      }

      if (reminder.readAt) {
        this.log('debug', `Reminder poll skipped read reminder. reminder_id=${reminder.id}`);
        continue;
      }

      if (this.seenReminderIds.has(reminder.id)) {
        this.log('debug', `Reminder poll skipped already-seen reminder. reminder_id=${reminder.id}`);
        continue;
      }

      this.seenReminderIds.set(reminder.id, Date.now());
      this.pruneSeenReminderIds();

      let deliveredAsSystem = false;
      if (this.onReminder) {
        deliveredAsSystem = Boolean(await this.onReminder(reminder));
      }
      this.log(
        'debug',
        `Reminder poll delivery evaluated. reminder_id=${reminder.id} delivered_system=${deliveredAsSystem}`,
      );

      if (deliveredAsSystem) {
        await this.ackSystemDelivery(reminder.id);
      }
    }
  }

  async ackSystemDelivery(reminderId) {
    if (!this.baseUrl || !reminderId) {
      return;
    }

    try {
      const headers = {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      };
      if (this.authToken) {
        headers.Authorization = `Bearer ${this.authToken}`;
      }

      await this.request(`${this.baseUrl}/api/calendar-reminders/${encodeURIComponent(reminderId)}/ack/`, {
        method: 'POST',
        headers,
        body: JSON.stringify({
          channel: 'system',
          deviceLabel: 'Electron Desktop',
        }),
      });
      this.log('debug', `Reminder system ack sent. reminder_id=${reminderId}`);
    } catch (error) {
      this.log('debug', `Reminder system ack failed for reminder_id=${reminderId}. error=${String(error)}`);
    }
  }

  async markReminderRead(rawReminderId, { deviceLabel = '' } = {}) {
    const reminderId = this.toPositiveInt(rawReminderId);
    if (!this.baseUrl || !reminderId) {
      return false;
    }

    const payload = {
      ids: [reminderId],
    };
    const normalizedDeviceLabel = typeof deviceLabel === 'string' ? deviceLabel.trim() : '';
    if (normalizedDeviceLabel) {
      payload.deviceLabel = normalizedDeviceLabel;
    }

    try {
      const headers = {
        Accept: 'application/json',
        'Content-Type': 'application/json',
      };
      if (this.authToken) {
        headers.Authorization = `Bearer ${this.authToken}`;
      }

      const response = await this.request(`${this.baseUrl}/api/calendar-reminders/inbox/mark-read/`, {
        method: 'POST',
        headers,
        body: JSON.stringify(payload),
      });
      if (!response.ok) {
        const body = await response.text();
        throw new Error(`HTTP ${response.status}: ${body.slice(0, 300)}`);
      }

      const body = await response.json().catch(() => ({}));
      const unreadCount = this.toNonNegativeInt(body?.unreadCount ?? body?.unread_count);
      if (this.onUnreadCount) {
        this.onUnreadCount(unreadCount);
      }

      this.log('debug', `Reminder marked read from desktop notification. reminder_id=${reminderId}`);
      return true;
    } catch (error) {
      this.log(
        'debug',
        `Reminder mark-read failed for reminder_id=${reminderId}. error=${String(error)}`,
      );
      return false;
    }
  }

  normalizeReminder(rawReminder) {
    const reminderId = this.toPositiveInt(rawReminder?.id);
    if (!reminderId) {
      return null;
    }

    return {
      id: reminderId,
      content: String(rawReminder?.content || ''),
      reminderDate: String(rawReminder?.reminderDate || rawReminder?.reminder_date || ''),
      reminderTime: String(rawReminder?.reminderTime || rawReminder?.reminder_time || ''),
      timezone: String(rawReminder?.timezone || ''),
      sentAt: rawReminder?.sentAt || rawReminder?.sent_at || null,
      readAt: rawReminder?.readAt || rawReminder?.read_at || null,
    };
  }

  pruneSeenReminderIds() {
    const now = Date.now();

    for (const [reminderId, seenAt] of this.seenReminderIds.entries()) {
      if (now - seenAt > MAX_SEEN_AGE_MS) {
        this.seenReminderIds.delete(reminderId);
      }
    }

    if (this.seenReminderIds.size <= MAX_SEEN_REMINDERS) {
      return;
    }

    const entriesByAge = [...this.seenReminderIds.entries()].sort((a, b) => a[1] - b[1]);
    const toDrop = this.seenReminderIds.size - MAX_SEEN_REMINDERS;
    for (let index = 0; index < toDrop; index += 1) {
      const reminderId = entriesByAge[index]?.[0];
      if (reminderId) {
        this.seenReminderIds.delete(reminderId);
      }
    }
  }

  normalizeOrigin(value) {
    if (!value) {
      return '';
    }

    try {
      return new URL(String(value)).origin;
    } catch {
      return '';
    }
  }

  toPositiveInt(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return null;
    }

    return Math.floor(parsed);
  }

  toNonNegativeInt(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return 0;
    }

    return Math.floor(parsed);
  }
}

module.exports = {
  ReminderFallbackPoller,
};
