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

export interface DesktopRuntimeStatus {
  available: boolean;
  running: boolean;
  healthy: boolean;
  reason?: string | null;
}

export interface DesktopSyncStatus {
  running: boolean;
  lastPushAt?: string | null;
  lastPullAt?: string | null;
  lastError?: string | null;
}

export interface DesktopVaultStatus {
  initialized: boolean;
  unlocked: boolean;
  vaultEpoch?: number | null;
  safeStorageAvailable?: boolean;
  lastError?: string | null;
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
  getRuntimeStatus?(): Promise<DesktopRuntimeStatus>;
  startLocalRuntime?(): Promise<DesktopRuntimeStatus>;
  stopLocalRuntime?(): Promise<DesktopRuntimeStatus>;
  getSyncStatus?(): Promise<DesktopSyncStatus>;
  getVaultStatus?(): Promise<DesktopVaultStatus>;
  unlockVault?(passphrase: string): Promise<DesktopVaultStatus>;
  lockVault?(): Promise<DesktopVaultStatus>;
  setVaultEpoch?(epoch: number): Promise<DesktopVaultStatus>;
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

  async getRuntimeStatus(): Promise<DesktopRuntimeStatus> {
    try {
      if (!this.api?.getRuntimeStatus) return { available: false, running: false, healthy: false };
      return (await this.api.getRuntimeStatus()) || { available: false, running: false, healthy: false };
    } catch {
      return { available: false, running: false, healthy: false };
    }
  }

  async startLocalRuntime(): Promise<DesktopRuntimeStatus> {
    try {
      if (!this.api?.startLocalRuntime) return { available: false, running: false, healthy: false };
      return (await this.api.startLocalRuntime()) || { available: false, running: false, healthy: false };
    } catch {
      return { available: false, running: false, healthy: false };
    }
  }

  async stopLocalRuntime(): Promise<DesktopRuntimeStatus> {
    try {
      if (!this.api?.stopLocalRuntime) return { available: false, running: false, healthy: false };
      return (await this.api.stopLocalRuntime()) || { available: false, running: false, healthy: false };
    } catch {
      return { available: false, running: false, healthy: false };
    }
  }

  async getSyncStatus(): Promise<DesktopSyncStatus> {
    try {
      if (!this.api?.getSyncStatus) return { running: false };
      return (await this.api.getSyncStatus()) || { running: false };
    } catch {
      return { running: false };
    }
  }

  async getVaultStatus(): Promise<DesktopVaultStatus> {
    try {
      if (!this.api?.getVaultStatus) return { initialized: false, unlocked: false };
      return (await this.api.getVaultStatus()) || { initialized: false, unlocked: false };
    } catch {
      return { initialized: false, unlocked: false };
    }
  }

  async unlockVault(passphrase: string): Promise<DesktopVaultStatus> {
    try {
      if (!this.api?.unlockVault) return { initialized: false, unlocked: false };
      return (await this.api.unlockVault(String(passphrase || ''))) || {
        initialized: false,
        unlocked: false,
      };
    } catch {
      return { initialized: false, unlocked: false };
    }
  }

  async lockVault(): Promise<DesktopVaultStatus> {
    try {
      if (!this.api?.lockVault) return { initialized: false, unlocked: false };
      return (await this.api.lockVault()) || { initialized: false, unlocked: false };
    } catch {
      return { initialized: false, unlocked: false };
    }
  }

  async setVaultEpoch(epoch: number): Promise<DesktopVaultStatus> {
    try {
      if (!this.api?.setVaultEpoch) return { initialized: false, unlocked: false };
      return (await this.api.setVaultEpoch(Number(epoch) || 1)) || {
        initialized: false,
        unlocked: false,
      };
    } catch {
      return { initialized: false, unlocked: false };
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
