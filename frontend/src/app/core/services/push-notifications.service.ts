import { HttpClient } from '@angular/common/http';
import { Inject, Injectable, PLATFORM_ID, inject } from '@angular/core';
import { isPlatformBrowser } from '@angular/common';
import { firstValueFrom } from 'rxjs';

import { ConfigService } from '@/core/services/config.service';
import { GlobalToastService } from '@/core/services/toast.service';

const FIREBASE_APP_COMPAT = 'https://www.gstatic.com/firebasejs/10.14.1/firebase-app-compat.js';
const FIREBASE_MESSAGING_COMPAT = 'https://www.gstatic.com/firebasejs/10.14.1/firebase-messaging-compat.js';

type PushPayload = {
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
  private readonly toast = inject(GlobalToastService);

  private initialized = false;
  private foregroundBound = false;
  private workerMessageBound = false;
  private missingConfigWarned = false;

  constructor(@Inject(PLATFORM_ID) private platformId: Object) {}

  async initialize(): Promise<void> {
    if (!isPlatformBrowser(this.platformId)) return;
    if (this.initialized) return;
    if (!('serviceWorker' in navigator) || !('Notification' in window)) return;

    const firebaseConfig = this.buildFirebaseConfig();
    const vapidKey = this.configService.settings.fcmVapidPublicKey?.trim();
    if (!firebaseConfig || !vapidKey) {
      this.warnMissingConfig(firebaseConfig, vapidKey);
      return;
    }

    try {
      await this.ensureFirebaseScripts();
      const registration = await navigator.serviceWorker.register('/firebase-messaging-sw.js');
      const readyRegistration = await navigator.serviceWorker.ready;
      const activeRegistration = readyRegistration || registration;
      if (!activeRegistration) {
        console.error('[PushNotificationsService] Service worker registration is undefined.');
        return;
      }
      if (!(activeRegistration as any).pushManager) {
        console.error(
          '[PushNotificationsService] Service worker registration has no pushManager. Aborting push token init.',
        );
        return;
      }
      this.postConfigToServiceWorker(activeRegistration, firebaseConfig);

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
        Notification.permission === 'granted'
          ? 'granted'
          : await Notification.requestPermission();
      if (permission !== 'granted') {
        return;
      }

      let token = '';
      try {
        token = await messaging.getToken({
          vapidKey,
          serviceWorkerRegistration: activeRegistration,
        });
      } catch (error) {
        const message = String((error as any)?.message || error || '');
        if (message.includes('pushManager')) {
          // Fallback for compat code paths that only work when registration is bound via useServiceWorker.
          token = await messaging.getToken({
            vapidKey,
            serviceWorkerRegistration: activeRegistration,
          });
        } else {
          throw error;
        }
      }
      if (token) {
        await this.registerToken(token);
      }

      this.initialized = true;
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
    if ((cfg.fcmWebStorageBucket || '').trim()) config['storageBucket'] = cfg.fcmWebStorageBucket!.trim();
    if ((cfg.fcmWebMeasurementId || '').trim())
      config['measurementId'] = cfg.fcmWebMeasurementId!.trim();

    return config;
  }

  private warnMissingConfig(firebaseConfig: Record<string, string> | null, vapidKey?: string): void {
    if (this.missingConfigWarned) return;

    const cfg = this.configService.settings;
    const missing: string[] = [];
    if (!((cfg.fcmSenderId || cfg.fcmProjectNumber || '').trim())) missing.push('fcmSenderId');
    if (!((cfg.fcmProjectId || '').trim())) missing.push('fcmProjectId');
    if (!((cfg.fcmWebApiKey || '').trim())) missing.push('fcmWebApiKey');
    if (!((cfg.fcmWebAppId || '').trim())) missing.push('fcmWebAppId');
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
    const data = payload.data || {};
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

    const title = payload.notification?.title || data['title'] || 'Notification';
    const body = payload.notification?.body || data['body'] || '';
    const message = body ? `${title}: ${body}` : title;
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

  private deviceLabel(): string {
    const platform = navigator.platform || 'unknown-platform';
    const lang = navigator.language || 'unknown-lang';
    return `${platform} (${lang})`;
  }
}
