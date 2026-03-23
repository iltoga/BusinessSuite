import { isPlatformBrowser } from '@angular/common';
import { HttpClient } from '@angular/common/http';
import { Inject, Injectable, PLATFORM_ID, inject } from '@angular/core';
import { Subject, firstValueFrom } from 'rxjs';

import { ConfigService } from '@/core/services/config.service';
import { DesktopBridgeService } from '@/core/services/desktop-bridge.service';
import { PushProxyFetchService } from '@/core/services/push-proxy-fetch.service';
import { ReminderDialogService } from '@/core/services/reminder-dialog.service';
import { GlobalToastService } from '@/core/services/toast.service';

const FIREBASE_APP_COMPAT = 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js';
const FIREBASE_MESSAGING_COMPAT =
  'https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js';

export type PushPayload = {
  data?: Record<string, string>;
  notification?: {
    title?: string;
    body?: string;
  };
};

declare global {
  interface Window {
    firebase?: any;
  }
}

@Injectable({ providedIn: 'root' })
export class PushNotificationsService {
  private readonly TOKEN_STORAGE_KEY = 'fcm_push_token';
  private readonly http = inject(HttpClient);
  private readonly configService = inject(ConfigService);
  private readonly desktopBridge = inject(DesktopBridgeService);
  private readonly pushProxyFetch = inject(PushProxyFetchService);
  private readonly reminderDialogs = inject(ReminderDialogService);
  private readonly toast = inject(GlobalToastService);

  private initialized = false;
  private foregroundBound = false;
  private workerMessageBound = false;
  private missingConfigWarned = false;
  private readonly incomingMessages = new Subject<PushPayload>();
  readonly incoming$ = this.incomingMessages.asObservable();

  constructor(@Inject(PLATFORM_ID) private platformId: Object) {}

  async initialize(): Promise<void> {
    if (!isPlatformBrowser(this.platformId)) return;
    if (this.initialized) return;
    if (!('serviceWorker' in navigator) || !('Notification' in window)) return;

    this.initialized = true;

    const firebaseConfig = this.buildFirebaseConfig();
    const vapidKey = this.configService.settings.fcmVapidPublicKey?.trim();
    if (!firebaseConfig || !vapidKey) {
      this.warnMissingConfig(firebaseConfig, vapidKey);
      return;
    }

    try {
      await this.ensureFirebaseScripts();

      // Register at a dedicated scope so it does NOT conflict with ngsw-worker.js
      // at scope /.  If both share scope /, firebase-messaging-sw.js stays in
      // "waiting" forever, never receives push events, and background notifications
      // never fire. A separate scope keeps the two registrations independent.
      const fcmSwUrl = this.buildServiceWorkerUrl(firebaseConfig);
      const registration = await navigator.serviceWorker.register(fcmSwUrl, {
        scope: '/_fcm/',
      });

      // Wait for the firebase SW to become active at its own scope.  On first
      // install there is no competing SW, so activation is nearly instant.
      // On subsequent loads with the same config URL the SW is already active.
      const activeRegistration = await this.awaitFcmSwActivation(registration);

      if (!activeRegistration) {
        console.error('[PushNotificationsService] Firebase messaging SW failed to activate.');
        return;
      }
      this.postConfigToServiceWorker(activeRegistration, firebaseConfig);
      this.postAuthTokenToServiceWorker(activeRegistration);

      const firebase = window.firebase;
      if (!firebase) return;
      if (!firebase.apps?.length) {
        firebase.initializeApp(firebaseConfig);
      }

      const messaging = firebase.messaging();
      // Compat SDK relies on useServiceWorker in some builds and can ignore
      // serviceWorkerRegistration passed to getToken().
      if (typeof messaging.useServiceWorker === 'function') {
        messaging.useServiceWorker(activeRegistration);
      }
      if (!this.foregroundBound) {
        messaging.onMessage((payload: PushPayload) => this.handleIncomingPayload(payload));
        this.foregroundBound = true;
      }

      if (!this.workerMessageBound) {
        navigator.serviceWorker.addEventListener('message', (event: MessageEvent) => {
          if (event?.data?.type !== 'PUSH_NOTIFICATION') return;
          this.handleIncomingPayload(event.data.payload as PushPayload);
        });
        this.workerMessageBound = true;
      }

      const permission =
        Notification.permission === 'granted' ? 'granted' : await Notification.requestPermission();
      if (permission !== 'granted') {
        return;
      }

      // Scope googleapis proxy interception to the token flow only.
      const fetchToken = async (): Promise<string> => {
        const nextToken = await this.pushProxyFetch.runWithGoogleApisProxy<string>(
          () =>
            messaging.getToken({
              vapidKey,
              serviceWorkerRegistration: activeRegistration,
            }) as Promise<string>,
        );
        return nextToken || '';
      };

      let token = '';
      try {
        token = await fetchToken();
      } catch (error) {
        const message = String((error as any)?.message || error || '');
        if (message.includes('pushManager')) {
          // Fallback for compat code paths that only work when registration is bound via useServiceWorker.
          token = await fetchToken();
        } else if (this.isRecoverableInstallationsError(error)) {
          console.warn(
            '[PushNotificationsService] Resetting stale Firebase installation state before retry.',
            this.describeError(error),
          );
          try {
            await this.resetFirebaseClientState();
            token = await fetchToken();
          } catch (retryError) {
            console.warn(
              '[PushNotificationsService] Push notifications unavailable: Firebase initialization failed after reset.',
              this.describeError(retryError),
            );
            return;
          }
        } else {
          throw error;
        }
      }
      if (token) {
        await this.registerToken(token);
      }
    } catch (error) {
      console.error('[PushNotificationsService] Initialization failed', error);
    }
  }

  private async ensureFirebaseScripts(): Promise<void> {
    await this.loadScriptOnce('firebase-app-compat', FIREBASE_APP_COMPAT);
    await this.loadScriptOnce('firebase-messaging-compat', FIREBASE_MESSAGING_COMPAT);
  }

  private loadScriptOnce(id: string, src: string): Promise<void> {
    return new Promise((resolve, reject) => {
      if (document.getElementById(id)) {
        resolve();
        return;
      }

      const script = document.createElement('script');
      script.id = id;
      script.src = src;
      script.async = true;
      script.defer = true;
      script.onload = () => resolve();
      script.onerror = () => reject(new Error(`Failed to load script ${src}`));
      document.head.appendChild(script);
    });
  }

  private buildFirebaseConfig(): Record<string, string> | null {
    const cfg = this.configService.settings;
    const messagingSenderId = (cfg.fcmSenderId || cfg.fcmProjectNumber || '').trim();
    const projectId = (cfg.fcmProjectId || '').trim();
    const apiKey = (cfg.fcmWebApiKey || '').trim();
    const appId = (cfg.fcmWebAppId || '').trim();

    if (!messagingSenderId || !projectId || !apiKey || !appId) {
      return null;
    }

    const config: Record<string, string> = {
      messagingSenderId,
      projectId,
      apiKey,
      appId,
    };

    if ((cfg.fcmWebAuthDomain || '').trim()) config['authDomain'] = cfg.fcmWebAuthDomain!.trim();
    if ((cfg.fcmWebStorageBucket || '').trim())
      config['storageBucket'] = cfg.fcmWebStorageBucket!.trim();
    if ((cfg.fcmWebMeasurementId || '').trim())
      config['measurementId'] = cfg.fcmWebMeasurementId!.trim();

    return config;
  }

  private warnMissingConfig(
    firebaseConfig: Record<string, string> | null,
    vapidKey?: string,
  ): void {
    if (this.missingConfigWarned) return;

    const cfg = this.configService.settings;
    const missing: string[] = [];
    if (!(cfg.fcmSenderId || cfg.fcmProjectNumber || '').trim()) missing.push('fcmSenderId');
    if (!(cfg.fcmProjectId || '').trim()) missing.push('fcmProjectId');
    if (!(cfg.fcmWebApiKey || '').trim()) missing.push('fcmWebApiKey');
    if (!(cfg.fcmWebAppId || '').trim()) missing.push('fcmWebAppId');
    if (!(vapidKey || '').trim()) missing.push('fcmVapidPublicKey');

    if (!firebaseConfig || missing.length > 0) {
      console.warn(
        `[PushNotificationsService] Push initialization skipped due to missing config: ${missing.join(', ') || 'firebaseConfig'}.`,
      );
    }

    this.missingConfigWarned = true;
  }

  private postConfigToServiceWorker(
    registration: ServiceWorkerRegistration,
    firebaseConfig: Record<string, string>,
  ): void {
    const workers = [registration.active, registration.waiting, registration.installing].filter(
      (worker): worker is ServiceWorker => !!worker,
    );
    workers.forEach((worker) => {
      worker.postMessage({
        type: 'FIREBASE_CONFIG',
        payload: firebaseConfig,
      });
    });
  }

  private postAuthTokenToServiceWorker(registration: ServiceWorkerRegistration): void {
    const token = localStorage.getItem('auth_token') || '';
    const workers = [registration.active, registration.waiting, registration.installing].filter(
      (worker): worker is ServiceWorker => !!worker,
    );
    workers.forEach((worker) => {
      worker.postMessage({ type: 'AUTH_TOKEN', token });
    });
  }

  /**
   * Waits for the firebase-messaging service worker to reach the "activated"
   * state on its own registration (scope /_fcm/).  On first install the
   * transition from "installing" → "activated" is nearly instant because
   * skipWaiting() is called in the SW's install handler.  On subsequent page
   * loads the SW is usually already active.
   */
  private awaitFcmSwActivation(
    registration: ServiceWorkerRegistration,
  ): Promise<ServiceWorkerRegistration | null> {
    if (registration.active?.state === 'activated') {
      return Promise.resolve(registration);
    }

    return new Promise<ServiceWorkerRegistration | null>((resolve) => {
      const deadline = setTimeout(() => {
        console.warn('[PushNotificationsService] Firebase SW activation timed out.');
        resolve(null);
      }, 10_000);

      const tryResolve = () => {
        if (registration.active?.state === 'activated') {
          clearTimeout(deadline);
          resolve(registration);
        }
      };

      const watch = (sw: ServiceWorker) => {
        sw.addEventListener('statechange', function listener() {
          if (sw.state === 'activated') {
            sw.removeEventListener('statechange', listener);
            clearTimeout(deadline);
            resolve(registration);
          } else if (sw.state === 'redundant') {
            sw.removeEventListener('statechange', listener);
            clearTimeout(deadline);
            resolve(null);
          }
        });
      };

      const sw = registration.installing || registration.waiting;
      if (sw) {
        watch(sw);
      } else {
        // Race: active may have just finished; check once more.
        tryResolve();
        if (registration.active?.state !== 'activated') {
          resolve(null);
        }
      }
    });
  }

  private buildServiceWorkerUrl(firebaseConfig: Record<string, string>): string {
    const params = new URLSearchParams(firebaseConfig);
    if (this.resolveServiceWorkerDebugFlag()) {
      params.set('pushDebug', '1');
      console.info('[PushNotificationsService] Service worker push debug logging enabled.');
    }
    const query = params.toString();
    return query ? `/firebase-messaging-sw.js?${query}` : '/firebase-messaging-sw.js';
  }

  private resolveServiceWorkerDebugFlag(): boolean {
    const queryValue = new URLSearchParams(window.location.search).get('pushDebug');
    if (queryValue !== null) {
      return this.parseBooleanFlag(queryValue);
    }

    try {
      const storageValue = localStorage.getItem('pushDebug');
      if (storageValue !== null) {
        return this.parseBooleanFlag(storageValue);
      }
    } catch {
      // Ignore storage errors (e.g. in restricted browser contexts).
    }

    return false;
  }

  private parseBooleanFlag(value: string): boolean {
    const normalized = value.trim().toLowerCase();
    return (
      normalized === '1' || normalized === 'true' || normalized === 'yes' || normalized === 'on'
    );
  }

  private async registerToken(token: string): Promise<void> {
    const previous = localStorage.getItem(this.TOKEN_STORAGE_KEY);
    if (previous && previous !== token) {
      await this.unregisterToken(previous);
    }

    await firstValueFrom(
      this.http.post('/api/push-notifications/register/', {
        token,
        device_label: this.deviceLabel(),
        user_agent: navigator.userAgent,
      }),
    );

    localStorage.setItem(this.TOKEN_STORAGE_KEY, token);
  }

  private async unregisterToken(token: string): Promise<void> {
    try {
      await firstValueFrom(this.http.post('/api/push-notifications/unregister/', { token }));
    } catch (error) {
      console.warn('[PushNotificationsService] Failed to unregister stale token', error);
    }
  }

  private handleIncomingPayload(payload: PushPayload): void {
    this.incomingMessages.next(payload);

    const data = payload.data || {};
    const title = payload.notification?.title || data['title'] || 'Daily Reminder';
    const body = payload.notification?.body || data['body'] || 'You have a new reminder.';
    const reminderId = this.parseReminderId(data['reminderId']);
    if (reminderId) {
      this.desktopBridge.publishPushReceipt(reminderId);
    }

    if (data['type'] === 'calendar_reminder') {
      if (reminderId) {
        this.desktopBridge.publishPushReminder({
          reminderId,
          title,
          body,
        });
      }
      this.reminderDialogs.enqueueFromPayload(payload);
      this.ackDeliveryChannel(data['reminderId'], 'in_app');
      return;
    }

    if (data['type'] === 'calendar_sync_failed') {
      const applicationId = data['applicationId'] || '?';
      const error = data['error'] || payload.notification?.body || 'Unknown error';
      const manualCopy = this.parseCalendarTaskCopy(data['calendarTaskCopy']);
      const copyText = manualCopy?.copyText || 'No manual task copy available.';
      this.toast.error(
        `Calendar sync failed for application #${applicationId}. Error: ${error}\n\nManual task copy:\n${copyText}`,
      );
      return;
    }

    const genericTitle = payload.notification?.title || data['title'] || 'Notification';
    const genericBody = payload.notification?.body || data['body'] || '';
    const message = genericBody ? `${genericTitle}: ${genericBody}` : genericTitle;
    this.toast.info(message);
  }

  private parseCalendarTaskCopy(raw: string | undefined): { copyText?: string } | null {
    if (!raw) return null;
    try {
      return JSON.parse(raw) as { copyText?: string };
    } catch {
      return null;
    }
  }

  private ackDeliveryChannel(reminderId: string | undefined, channel: string): void {
    if (!reminderId) return;
    const deviceLabel = this.deviceLabel();
    firstValueFrom(
      this.http.post(`/api/calendar-reminders/${encodeURIComponent(reminderId)}/ack/`, {
        channel,
        deviceLabel,
      }),
    ).catch(() => {
      // Best effort — ignore failures
    });
  }

  private deviceLabel(): string {
    const platform = navigator.platform || 'unknown-platform';
    const lang = navigator.language || 'unknown-lang';
    return `${platform} (${lang})`;
  }

  private parseReminderId(rawValue: string | undefined): number | null {
    const parsed = Number(rawValue);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return Math.floor(parsed);
  }

  private isRecoverableInstallationsError(error: unknown): boolean {
    const message = String((error as any)?.message || error || '').toLowerCase();
    return (
      message.includes('installations/request-failed') &&
      (message.includes('token_not_valid') || message.includes('given token not valid'))
    );
  }

  private async resetFirebaseClientState(): Promise<void> {
    await this.deleteFirebaseApps();
    await Promise.all([
      this.deleteIndexedDbIfPresent('firebase-installations-database'),
      this.deleteIndexedDbIfPresent('firebase-messaging-database'),
    ]);
  }

  private async deleteFirebaseApps(): Promise<void> {
    const firebase = window.firebase;
    const apps = Array.isArray(firebase?.apps) ? firebase.apps : [];
    await Promise.all(
      apps.map(async (app: any) => {
        if (typeof app?.delete !== 'function') {
          return;
        }
        try {
          await app.delete();
        } catch (error) {
          console.warn(
            '[PushNotificationsService] Failed to delete Firebase app during reset',
            error,
          );
        }
      }),
    );
  }

  private deleteIndexedDbIfPresent(name: string): Promise<void> {
    if (typeof indexedDB === 'undefined') {
      return Promise.resolve();
    }

    return new Promise((resolve) => {
      try {
        const request = indexedDB.deleteDatabase(name);
        request.onsuccess = () => resolve();
        request.onerror = () => resolve();
        request.onblocked = () => resolve();
      } catch {
        resolve();
      }
    });
  }

  private describeError(error: unknown): { name?: string; message?: string } {
    if (error instanceof Error) {
      return {
        name: error.name,
        message: error.message,
      };
    }

    return {
      message: String(error ?? 'Unknown push notification error'),
    };
  }
}
