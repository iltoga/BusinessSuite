/* global firebase, importScripts, self, clients */

importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js');
importScripts('https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js');

let initialized = false;

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

function initializeFirebase(config) {
  if (initialized) return;
  if (!config || !config.messagingSenderId) return;

  firebase.initializeApp(config);
  const messaging = firebase.messaging();

  messaging.onBackgroundMessage((payload) => {
    const notificationTitle =
      payload?.notification?.title || payload?.data?.title || 'Revis Bali CRM';
    const notificationOptions = {
      body: payload?.notification?.body || payload?.data?.body || '',
      data: {
        link: payload?.data?.link || '/',
        payload,
      },
    };

    self.registration.showNotification(notificationTitle, notificationOptions);
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((allClients) => {
      allClients.forEach((client) => {
        client.postMessage({
          type: 'PUSH_NOTIFICATION',
          payload,
        });
      });
    });
  });

  initialized = true;
}

// Firebase messaging must be initialized during initial script evaluation
// so push-related handlers are registered immediately.
initializeFirebase(configFromWorkerUrl());

self.addEventListener('message', (event) => {
  if (event?.data?.type !== 'FIREBASE_CONFIG') return;
  initializeFirebase(event.data.payload);
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const link = event.notification?.data?.link || '/';

  event.waitUntil(
    clients.matchAll({ type: 'window', includeUncontrolled: true }).then((allClients) => {
      for (const client of allClients) {
        if ('focus' in client) {
          client.postMessage({
            type: 'PUSH_NOTIFICATION',
            payload: event.notification?.data?.payload || {},
          });
          return client.focus();
        }
      }
      if (clients.openWindow) {
        return clients.openWindow(link);
      }
      return undefined;
    }),
  );
});
