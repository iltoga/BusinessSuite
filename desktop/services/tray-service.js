'use strict';

const { Menu, Tray, nativeImage } = require('electron');

class TrayService {
  constructor({
    appName,
    iconPath,
    unreadIconPath,
    onOpen,
    onCheckForUpdates,
    onQuit,
    onToggleLaunchAtLogin,
    getLaunchAtLogin,
  }) {
    this.appName = appName || 'Revis Bali CRM';
    this.onOpen = typeof onOpen === 'function' ? onOpen : () => {};
    this.onCheckForUpdates =
      typeof onCheckForUpdates === 'function' ? onCheckForUpdates : () => {};
    this.onQuit = typeof onQuit === 'function' ? onQuit : () => {};
    this.onToggleLaunchAtLogin =
      typeof onToggleLaunchAtLogin === 'function' ? onToggleLaunchAtLogin : () => false;
    this.getLaunchAtLogin = typeof getLaunchAtLogin === 'function' ? getLaunchAtLogin : () => false;

    this.defaultIcon = this.loadIcon(iconPath, 18);
    this.unreadIcon = this.loadIcon(unreadIconPath, 18) || this.defaultIcon;
    this.overlayIcon = this.loadIcon(unreadIconPath, 16);

    this.unreadCount = 0;
    this.tray = null;
  }

  initialize() {
    if (this.tray) {
      return;
    }

    this.tray = new Tray(this.defaultIcon);
    this.tray.setToolTip(this.buildTooltip());
    this.applyMacBadgeTitle();
    this.tray.on('click', () => this.onOpen());
    this.tray.on('double-click', () => this.onOpen());

    this.refreshMenu();
  }

  setUnreadCount(rawCount) {
    const parsed = Number(rawCount);
    this.unreadCount = Number.isFinite(parsed) && parsed > 0 ? Math.floor(parsed) : 0;

    if (!this.tray) {
      return;
    }

    this.tray.setToolTip(this.buildTooltip());
    this.tray.setImage(this.unreadCount > 0 ? this.unreadIcon : this.defaultIcon);
    this.applyMacBadgeTitle();
    this.refreshMenu();
  }

  getOverlayIcon() {
    if (!this.overlayIcon || this.overlayIcon.isEmpty()) {
      return null;
    }

    return this.overlayIcon;
  }

  refreshMenu() {
    if (!this.tray) {
      return;
    }

    const supportsLaunchAtLogin = process.platform === 'darwin' || process.platform === 'win32';

    const menu = Menu.buildFromTemplate([
      {
        label: this.unreadCount > 0 ? `Unread reminders: ${this.unreadCount}` : 'Unread reminders: 0',
        enabled: false,
      },
      { type: 'separator' },
      {
        label: 'Open CRM',
        click: () => this.onOpen(),
      },
      {
        label: 'Check for Updates',
        click: () => this.onCheckForUpdates(),
      },
      { type: 'separator' },
      {
        type: 'checkbox',
        label: 'Launch at Login',
        checked: supportsLaunchAtLogin ? Boolean(this.getLaunchAtLogin()) : false,
        enabled: supportsLaunchAtLogin,
        click: (menuItem) => {
          this.onToggleLaunchAtLogin(Boolean(menuItem?.checked));
          this.refreshMenu();
        },
      },
      { type: 'separator' },
      {
        label: 'Quit',
        click: () => this.onQuit(),
      },
    ]);

    this.tray.setContextMenu(menu);
  }

  destroy() {
    if (!this.tray) {
      return;
    }

    this.tray.destroy();
    this.tray = null;
  }

  buildTooltip() {
    if (this.unreadCount > 0) {
      return `${this.appName} (${this.unreadCount} unread)`;
    }

    return this.appName;
  }

  applyMacBadgeTitle() {
    if (!this.tray || process.platform !== 'darwin') {
      return;
    }

    const countLabel = this.unreadCount > 0 ? String(this.unreadCount) : '';
    try {
      this.tray.setTitle(countLabel ? ` ${countLabel}` : '', { fontType: 'monospacedDigit' });
    } catch {
      this.tray.setTitle(countLabel ? ` ${countLabel}` : '');
    }
  }

  loadIcon(filePath, size) {
    if (!filePath) {
      return nativeImage.createEmpty();
    }

    const image = nativeImage.createFromPath(filePath);
    if (image.isEmpty()) {
      return nativeImage.createEmpty();
    }

    return image.resize({ width: size, height: size });
  }
}

module.exports = {
  TrayService,
};
