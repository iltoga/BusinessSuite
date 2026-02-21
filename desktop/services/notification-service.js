'use strict';

const { Notification } = require('electron');

const ACTION_MARK_READ = 0;
const ACTION_SNOOZE_15_MIN = 1;

class NotificationService {
  constructor({ appName = 'Revis Bali CRM', onClick, onClose, onMarkRead, onSnooze, log } = {}) {
    this.appName = appName;
    this.onClick = typeof onClick === 'function' ? onClick : () => {};
    this.onClose = typeof onClose === 'function' ? onClose : () => {};
    this.onMarkRead = typeof onMarkRead === 'function' ? onMarkRead : () => {};
    this.onSnooze = typeof onSnooze === 'function' ? onSnooze : () => {};
    this.log = typeof log === 'function' ? log : () => {};
  }

  showReminderNotification(reminder) {
    const reminderId = this.toPositiveInt(reminder?.id);
    if (!this.isNotificationSupported()) {
      this.log('debug', `System notification skipped (unsupported). reminder_id=${reminderId ?? 'unknown'}`);
      return false;
    }

    const title = String(reminder?.title || 'Reminder');
    const body = String(reminder?.content || 'You have a reminder.');
    this.log(
      'debug',
      `System notification emission requested. reminder_id=${reminderId ?? 'unknown'} body_len=${body.length}`,
    );

    const supportsActions = process.platform === 'darwin' || process.platform === 'win32';
    const notification = new Notification({
      title,
      subtitle: this.appName,
      body,
      silent: false,
      actions: supportsActions
        ? [
            { type: 'button', text: 'Mark as Read' },
            { type: 'button', text: 'Snooze 15m' },
          ]
        : [],
      closeButtonText: 'Dismiss',
    });

    let handledByAction = false;

    notification.on('click', () => {
      if (handledByAction) {
        return;
      }

      this.log('debug', `System notification clicked. reminder_id=${reminderId ?? 'unknown'}`);
      this.onClick({
        reminderId,
        route: '/reminders',
      });
    });

    notification.on('action', (event, actionIndex) => {
      const fallbackIndex = Number(event?.actionIndex);
      const index = Number.isFinite(actionIndex)
        ? Number(actionIndex)
        : Number.isFinite(fallbackIndex)
          ? fallbackIndex
          : -1;

      if (index === ACTION_MARK_READ) {
        handledByAction = true;
        this.log('debug', `System notification action Mark as Read. reminder_id=${reminderId ?? 'unknown'}`);
        this.onMarkRead({
          reminderId,
          route: '/reminders',
        });
        return;
      }

      if (index === ACTION_SNOOZE_15_MIN) {
        handledByAction = true;
        this.log('debug', `System notification action Snooze 15m. reminder_id=${reminderId ?? 'unknown'}`);
        this.onSnooze({
          reminderId,
          route: '/reminders',
          minutes: 15,
        });
      }
    });

    notification.on('close', () => {
      if (handledByAction) {
        this.log(
          'debug',
          `System notification close suppressed after action. reminder_id=${reminderId ?? 'unknown'}`,
        );
        return;
      }

      this.log('debug', `System notification closed. reminder_id=${reminderId ?? 'unknown'}`);
      this.onClose({
        reminderId,
        route: '/reminders',
      });
    });

    notification.show();
    this.log('debug', `System notification shown. reminder_id=${reminderId ?? 'unknown'}`);
    return true;
  }

  isNotificationSupported() {
    if (typeof Notification?.isSupported !== 'function') {
      return true;
    }

    return Notification.isSupported();
  }

  toPositiveInt(value) {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) {
      return null;
    }

    return Math.floor(parsed);
  }
}

module.exports = {
  NotificationService,
};
