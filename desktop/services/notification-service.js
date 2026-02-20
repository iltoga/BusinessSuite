'use strict';

const { Notification } = require('electron');

class NotificationService {
  constructor({ appName = 'Revis Bali CRM', onClick, onClose, log } = {}) {
    this.appName = appName;
    this.onClick = typeof onClick === 'function' ? onClick : () => {};
    this.onClose = typeof onClose === 'function' ? onClose : () => {};
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

    const notification = new Notification({
      title,
      subtitle: this.appName,
      body,
      silent: false,
    });

    notification.on('click', () => {
      this.log('debug', `System notification clicked. reminder_id=${reminderId ?? 'unknown'}`);
      this.onClick({
        reminderId,
        route: '/reminders',
      });
    });

    notification.on('close', () => {
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
