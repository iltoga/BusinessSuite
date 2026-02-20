/* global firebase, importScripts, self, clients, fetch */

importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

// Activate immediately on install so push events are handled without competing
// with ngsw-worker.js. This SW is registered at scope /_fcm/ (separate scope)
// so skipWaiting() here is safe — it doesn't displace ngsw-worker.js.
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', (event) => event.waitUntil(clients.claim()));

let initialized = false;
let debugEnabled = false;

const IDB_NAME = 'fcm-sw-data';
const IDB_STORE = 'config';
const IDB_VERSION = 1;

function openIdb() {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(IDB_NAME, IDB_VERSION);
    req.onupgradeneeded = () => req.result.createObjectStore(IDB_STORE);
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function saveAuthToken(token) {
  return openIdb()
    .then((db) => {
      return new Promise((resolve, reject) => {
        const tx = db.transaction(IDB_STORE, 'readwrite');
        tx.objectStore(IDB_STORE).put(token, 'authToken');
        tx.oncomplete = () => {
          db.close();
          resolve();
        };
        tx.onerror = () => {
          db.close();
          reject(tx.error);
        };
      });
    })
    .catch(() => {});
}

function loadAuthToken() {
  return openIdb()
    .then((db) => {
      return new Promise((resolve) => {
        const tx = db.transaction(IDB_STORE, 'readonly');
        const getReq = tx.objectStore(IDB_STORE).get('authToken');
        getReq.onsuccess = () => {
          db.close();
          resolve(getReq.result || '');
        };
        getReq.onerror = () => {
          db.close();
          resolve('');
        };
      });
    })
    .catch(() => '');
}

function parseBooleanFlag(value) {
  if (value === undefined || value === null) return false;
  const normalized = String(value).trim().toLowerCase();
  return normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on';
}

function debugLog(message, details) {
  if (!debugEnabled) return;
  if (details !== undefined) {
    console.log(`[Push SW] ${message}`, details);
    return;
  }
  console.log(`[Push SW] ${message}`);
}

function swDeviceLabel() {
  const nav = self.navigator || {};
  const platform = nav.platform || 'unknown-platform';
  const lang = nav.language || 'unknown-lang';
  return `${platform} (${lang}) [SW]`.slice(0, 255);
}

function configFromWorkerUrl() {
  try {
    const url = new URL(self.location.href);
    const config = {};
    url.searchParams.forEach((value, key) => {
      if (!value) return;
      config[key] = value;
    });
    return Object.keys(config).length > 0 ? config : null;
  } catch {
    return null;
  }
}

/**
 * Acknowledge reminder delivery channel to the backend.
 * Best-effort — failures are silently ignored.
 */
async function ackDeliveryChannel(reminderId, channel) {
  if (!reminderId) return;
  try {
    const token = await loadAuthToken();
    if (!token) {
      debugLog('ackDeliveryChannel skipped — no auth token in IndexedDB');
      return;
    }
    await fetch(`/api/calendar-reminders/${encodeURIComponent(reminderId)}/ack/`, {
      method: 'POST',
      headers: {
        'Content-Type': 'application/json',
        Authorization: `Bearer ${token}`,
      },
      body: JSON.stringify({ channel, deviceLabel: swDeviceLabel() }),
    });
    debugLog('Acked delivery channel', { reminderId, channel });
  } catch {
    // Best effort — ignore network errors in SW context
  }
}

function initializeFirebase(config) {
  if (initialized) return;
  if (!config) return;

  const firebaseConfig = { ...config };
  debugEnabled = parseBooleanFlag(firebaseConfig.pushDebug);
  delete firebaseConfig.pushDebug;

  if (!firebaseConfig.messagingSenderId) return;

  firebase.initializeApp(firebaseConfig);
  const messaging = firebase.messaging();
  debugLog('Initialized Firebase messaging service worker.', {
    messagingSenderId: firebaseConfig.messagingSenderId,
    projectId: firebaseConfig.projectId || null,
  });

  messaging.onBackgroundMessage(async (payload) => {
    debugLog('onBackgroundMessage fired', payload);

    try {
      const payloadData = payload?.data || {};
      const fallbackLink = payload?.fcmOptions?.link || '/';
      const link = payloadData.link || fallbackLink || '/';
      const reminderTag =
        payloadData.type === 'calendar_reminder' && payloadData.reminderId
          ? `calendar-reminder-${payloadData.reminderId}`
          : '';
      const notificationTag = payloadData.tag || reminderTag || undefined;

      const notificationTitle =
        payload?.notification?.title || payloadData.title || 'Revis Bali CRM';
      const notificationOptions = {
        body: payload?.notification?.body || payloadData.body || '',
        icon: payloadData.icon || '/icons/icon-192x192.png',
        badge: payloadData.badge || '/icons/icon-72x72.png',
        tag: notificationTag,
        renotify: Boolean(notificationTag),
        requireInteraction: payloadData.type === 'calendar_reminder',
        timestamp: Date.now(),
        data: {
          link,
          payload,
          deliveryChannel: 'system',
        },
      };

      let visibleClients = [];
      try {
        const allClients = await clients.matchAll({ type: 'window', includeUncontrolled: true });
        visibleClients = allClients.filter(
          (client) => client.visibilityState === 'visible' || client.focused === true,
        );
      } catch (err) {
        debugLog('clients.matchAll failed, assuming no visible clients', err);
      }

      if (visibleClients.length > 0) {
        debugLog('Push routed to in-app branch (no OS notification).', {
          visibleClients: visibleClients.length,
          reminderId: payloadData.reminderId || null,
        });
        visibleClients.forEach((client) => {
          client.postMessage({
            type: 'PUSH_NOTIFICATION',
            payload,
            channel: 'in_app',
          });
        });
        return;
      }

      // No visible app windows — show OS notification.
      debugLog('Push routed to OS notification branch.', {
        reminderId: payloadData.reminderId || null,
      });
      await self.registration.showNotification(notificationTitle, notificationOptions);

      // Acknowledge system delivery for calendar reminders.
      if (payloadData.type === 'calendar_reminder' && payloadData.reminderId) {
        await ackDeliveryChannel(payloadData.reminderId, 'system');
      }
    } catch (err) {
      // Last-resort: always show *some* notification so the push isn't lost.
      debugLog('onBackgroundMessage error — showing fallback notification', err);
      try {
        await self.registration.showNotification('Revis Bali CRM', {
          body: 'You have a new notification.',
          icon: '/icons/icon-192x192.png',
        });
      } catch {
        // Nothing we can do
      }
    }
  });

  initialized = true;
}

// Firebase messaging must be initialized during initial script evaluation
// so push-related handlers are registered immediately.
initializeFirebase(configFromWorkerUrl());

self.addEventListener('message', (event) => {
  if (!event?.data?.type) return;

  if (event.data.type === 'FIREBASE_CONFIG') {
    initializeFirebase(event.data.payload);
    return;
  }

  if (event.data.type === 'AUTH_TOKEN') {
    const token = event.data.token || '';
    saveAuthToken(token);
    debugLog('Auth token persisted to IndexedDB');
    return;
  }
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const notifData = event.notification?.data || {};
  const link = notifData.link || '/';
  const payload = notifData.payload || {};
  const deliveryChannel = notifData.deliveryChannel || 'system';
  debugLog('Notification click received.', {
    link,
    reminderId: payload?.data?.reminderId || null,
    deliveryChannel,
  });

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then(async (allClients) => {
      for (const client of allClients) {
        if ('navigate' in client && link) {
          try {
            await client.navigate(link);
          } catch {
            // Ignore navigation errors and continue with focus fallback.
          }
        }
        if ('focus' in client) {
          client.postMessage({
            type: 'PUSH_NOTIFICATION',
            payload,
            channel: deliveryChannel,
          });
          return client.focus();
        }
      }
      if (clients.openWindow) {
        debugLog('Opening new window from notification click.', { link });
        return clients.openWindow(link);
      }
      return undefined;
    }),
  );
});
