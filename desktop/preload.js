'use strict';

const { contextBridge, ipcRenderer } = require('electron');

const toNullableToken = (value) => {
  if (typeof value !== 'string') {
    return null;
  }

  const trimmed = value.trim();
  return trimmed || null;
};

const toNonNegativeInt = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 0;
  }

  return Math.floor(parsed);
};

const toPositiveInt = (value) => {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }

  return Math.floor(parsed);
};

contextBridge.exposeInMainWorld('revisDesktop', {
  isDesktop() {
    return true;
  },

  publishAuthToken(token) {
    ipcRenderer.send('desktop:auth-token', toNullableToken(token));
  },

  publishUnreadCount(count) {
    ipcRenderer.send('desktop:unread-count', toNonNegativeInt(count));
  },

  publishPushReceipt(reminderId) {
    const normalized = toPositiveInt(reminderId);
    if (!normalized) {
      return;
    }

    ipcRenderer.send('desktop:push-receipt', normalized);
  },

  publishPushReminder(payload) {
    if (!payload || typeof payload !== 'object') {
      return;
    }

    const reminderId = toPositiveInt(payload.reminderId);
    if (!reminderId) {
      return;
    }

    const body = String(payload.body || '').trim();
    if (!body) {
      return;
    }

    const title = String(payload.title || 'Reminder').trim() || 'Reminder';
    ipcRenderer.send('desktop:push-reminder', {
      reminderId,
      title,
      body,
    });
  },

  onReminderOpen(handler) {
    if (typeof handler !== 'function') {
      return () => {};
    }

    const listener = (_event, payload) => {
      handler(payload || {});
    };

    ipcRenderer.on('desktop:reminder-open', listener);
    return () => {
      ipcRenderer.removeListener('desktop:reminder-open', listener);
    };
  },

  getLaunchAtLogin() {
    return ipcRenderer.invoke('desktop:launch-at-login:get');
  },

  setLaunchAtLogin(enabled) {
    return ipcRenderer.invoke('desktop:launch-at-login:set', Boolean(enabled));
  },
});
