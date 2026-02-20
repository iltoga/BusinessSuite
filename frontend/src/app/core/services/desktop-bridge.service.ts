import { isPlatformBrowser } from '@angular/common';
import { Injectable, PLATFORM_ID, inject } from '@angular/core';

export interface DesktopReminderOpenPayload {
  reminderId?: number | null;
  route?: string;
}

export interface DesktopPushReminderPayload {
  reminderId: number;
  title?: string;
  body: string;
}

type ReminderOpenHandler = (payload: DesktopReminderOpenPayload) => void;

export interface RevisDesktopApi {
  isDesktop(): boolean;
  publishAuthToken(token: string | null): void;
  publishUnreadCount(count: number): void;
  publishPushReceipt(reminderId: number): void;
  publishPushReminder(payload: DesktopPushReminderPayload): void;
  onReminderOpen(handler: ReminderOpenHandler): () => void;
  getLaunchAtLogin?(): Promise<boolean>;
  setLaunchAtLogin?(enabled: boolean): Promise<boolean>;
}

declare global {
  interface Window {
    revisDesktop?: RevisDesktopApi;
  }
}

@Injectable({
  providedIn: 'root',
})
export class DesktopBridgeService {
  private readonly platformId = inject(PLATFORM_ID);
  private readonly browser = isPlatformBrowser(this.platformId);

  private get api(): RevisDesktopApi | undefined {
    if (!this.browser) return undefined;
    return window.revisDesktop;
  }

  isDesktop(): boolean {
    try {
      return Boolean(this.api?.isDesktop?.());
    } catch {
      return false;
    }
  }

  publishAuthToken(token: string | null): void {
    try {
      this.api?.publishAuthToken(token);
    } catch {
      // Best effort bridge for desktop mode.
    }
  }

  publishUnreadCount(count: number): void {
    try {
      this.api?.publishUnreadCount(this.toNonNegativeInt(count));
    } catch {
      // Best effort bridge for desktop mode.
    }
  }

  publishPushReceipt(reminderId: number): void {
    const normalized = this.toPositiveInt(reminderId);
    if (!normalized) return;

    try {
      this.api?.publishPushReceipt(normalized);
    } catch {
      // Best effort bridge for desktop mode.
    }
  }

  publishPushReminder(payload: DesktopPushReminderPayload): void {
    const reminderId = this.toPositiveInt(payload?.reminderId);
    const body = String(payload?.body || '').trim();
    if (!reminderId || !body) return;

    try {
      this.api?.publishPushReminder({
        reminderId,
        title: String(payload?.title || 'Reminder').trim() || 'Reminder',
        body,
      });
    } catch {
      // Best effort bridge for desktop mode.
    }
  }

  onReminderOpen(handler: ReminderOpenHandler): () => void {
    try {
      if (!this.api?.onReminderOpen) return () => {};
      return this.api.onReminderOpen(handler);
    } catch {
      return () => {};
    }
  }

  async getLaunchAtLogin(): Promise<boolean> {
    try {
      if (!this.api?.getLaunchAtLogin) return false;
      return Boolean(await this.api.getLaunchAtLogin());
    } catch {
      return false;
    }
  }

  async setLaunchAtLogin(enabled: boolean): Promise<boolean> {
    try {
      if (!this.api?.setLaunchAtLogin) return false;
      return Boolean(await this.api.setLaunchAtLogin(Boolean(enabled)));
    } catch {
      return false;
    }
  }

  private toPositiveInt(value: number): number | null {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return null;
    return Math.floor(parsed);
  }

  private toNonNegativeInt(value: number): number {
    const parsed = Number(value);
    if (!Number.isFinite(parsed) || parsed <= 0) return 0;
    return Math.floor(parsed);
  }
}
