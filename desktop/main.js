"use strict";

const { app, BrowserWindow, dialog, ipcMain, shell } = require("electron");
const fs = require("node:fs");
const path = require("node:path");
let autoUpdater = null;
try {
  ({ autoUpdater } = require("electron-updater"));
} catch {
  autoUpdater = null;
}

const { NotificationService } = require("./services/notification-service");
const {
  ReminderFallbackPoller,
} = require("./services/reminder-fallback-poller");
const { TrayService } = require("./services/tray-service");

const DEFAULT_START_URL = "https://crm.revisbali.com";
const APP_NAME = "Revis Bali CRM";
const RENDERER_UNREAD_SYNC_TTL_MS = 20_000;
const DEFAULT_REMINDER_POLL_INTERVAL_MS = 15_000;
const INITIAL_UPDATE_CHECK_DELAY_MS = 10_000;
const UPDATE_CHECK_INTERVAL_MS = 4 * 60 * 60 * 1000;

loadDesktopEnvFile();

const levelPriority = {
  debug: 10,
  info: 20,
  warn: 30,
  error: 40,
};

const configuredLevel = String(
  process.env.DESKTOP_LOG_LEVEL || "info",
).toLowerCase();
const currentLevel = levelPriority[configuredLevel] ?? levelPriority.info;

const startUrl = resolveStartUrl(
  process.env.DESKTOP_START_URL || DEFAULT_START_URL,
);
const allowedOrigin = normalizeOrigin(
  process.env.DESKTOP_ALLOWED_ORIGIN || startUrl.origin,
);
const reminderPollIntervalMs = resolveReminderPollInterval(
  process.env.DESKTOP_REMINDER_POLL_INTERVAL_MS,
);

let isQuitting = false;
let mainWindow = null;
let trayService = null;
let notificationService = null;
let reminderPoller = null;
let sessionSecurityConfigured = false;
let unreadCount = 0;
let lastRendererUnreadSyncAt = 0;
let lastRendererUnreadCount = 0;
let updateCheckInProgress = false;
let updateDownloadInProgress = false;
let updatePromptInProgress = false;
let updateCheckIntervalHandle = null;
let updateInstallInProgress = false;

const gotSingleInstanceLock = app.requestSingleInstanceLock();
if (!gotSingleInstanceLock) {
  app.quit();
}

function loadDesktopEnvFile() {
  const envFilePath = path.join(__dirname, ".env");
  let raw = "";

  try {
    raw = fs.readFileSync(envFilePath, "utf8");
  } catch {
    return;
  }

  for (const line of raw.split(/\r?\n/)) {
    const trimmed = line.trim();
    if (!trimmed || trimmed.startsWith("#")) {
      continue;
    }

    const equalsIndex = trimmed.indexOf("=");
    if (equalsIndex <= 0) {
      continue;
    }

    const key = trimmed
      .slice(0, equalsIndex)
      .trim()
      .replace(/^export\s+/, "");
    if (!key || process.env[key] !== undefined) {
      continue;
    }

    let value = trimmed.slice(equalsIndex + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }

    process.env[key] = value;
  }
}

function log(level, message, extra) {
  const numericLevel = levelPriority[level] ?? levelPriority.info;
  if (numericLevel < currentLevel) {
    return;
  }

  const suffix = extra === undefined ? "" : ` ${JSON.stringify(extra)}`;
  const line = `[Desktop] [${level.toUpperCase()}] ${message}${suffix}`;

  if (level === "error") {
    console.error(line);
    return;
  }

  if (level === "warn") {
    console.warn(line);
    return;
  }

  if (level === "debug") {
    console.debug(line);
    return;
  }

  console.info(line);
}

function resolveStartUrl(rawValue) {
  try {
    return new URL(String(rawValue || DEFAULT_START_URL));
  } catch {
    return new URL(DEFAULT_START_URL);
  }
}

function normalizeOrigin(rawValue) {
  try {
    return new URL(String(rawValue)).origin;
  } catch {
    return "";
  }
}

function resolveReminderPollInterval(rawValue) {
  const parsed = Number(rawValue);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return DEFAULT_REMINDER_POLL_INTERVAL_MS;
  }

  return Math.floor(parsed);
}

function isAllowedUrl(rawUrl) {
  if (rawUrl === "about:blank") {
    return true;
  }

  try {
    const parsed = new URL(rawUrl);
    return parsed.origin === allowedOrigin;
  } catch {
    return false;
  }
}

function toNonNegativeInt(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return 0;
  }

  return Math.floor(parsed);
}

function toPositiveInt(value) {
  const parsed = Number(value);
  if (!Number.isFinite(parsed) || parsed <= 0) {
    return null;
  }

  return Math.floor(parsed);
}

function normalizeDesktopPushReminder(rawPayload) {
  if (!rawPayload || typeof rawPayload !== "object") {
    return null;
  }

  const reminderId = toPositiveInt(rawPayload.reminderId ?? rawPayload.id);
  if (!reminderId) {
    return null;
  }

  const body = String(rawPayload.body ?? rawPayload.content ?? "").trim();
  if (!body) {
    return null;
  }

  const title = String(rawPayload.title ?? "Reminder").trim() || "Reminder";
  return {
    id: reminderId,
    title,
    content: body,
  };
}

function shouldHideInsteadOfClose() {
  return !isQuitting;
}

function getWindowIconPath() {
  return path.join(__dirname, "assets", "icons", "icon-256x256.png");
}

function createWindow() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    return mainWindow;
  }

  mainWindow = new BrowserWindow({
    width: 1360,
    height: 880,
    minWidth: 1120,
    minHeight: 700,
    show: false,
    title: APP_NAME,
    autoHideMenuBar: true,
    icon: getWindowIconPath(),
    webPreferences: {
      preload: path.join(__dirname, "preload.js"),
      contextIsolation: true,
      sandbox: true,
      nodeIntegration: false,
      webSecurity: true,
    },
  });

  configureNavigationGuards(mainWindow);
  configurePermissionHandlers(mainWindow.webContents.session);

  mainWindow.once("ready-to-show", () => {
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    mainWindow.show();
  });

  mainWindow.on("close", (event) => {
    if (!shouldHideInsteadOfClose()) {
      return;
    }

    event.preventDefault();
    if (!mainWindow || mainWindow.isDestroyed()) {
      return;
    }

    mainWindow.hide();
  });

  mainWindow.on("closed", () => {
    mainWindow = null;
  });

  mainWindow.webContents.on(
    "did-fail-load",
    (_event, errorCode, errorDescription) => {
      log(
        "error",
        `Main window failed to load (code=${errorCode}): ${String(errorDescription)}`,
      );
    },
  );

  mainWindow.webContents.on("did-finish-load", () => {
    void syncAuthTokenFromRenderer();
  });

  void mainWindow.loadURL(startUrl.href).catch((error) => {
    log("error", `Unable to load start URL: ${String(error)}`);
  });

  return mainWindow;
}

function configureNavigationGuards(windowRef) {
  windowRef.webContents.setWindowOpenHandler(({ url }) => {
    if (isAllowedUrl(url)) {
      return { action: "allow" };
    }

    void shell.openExternal(url);
    return { action: "deny" };
  });

  windowRef.webContents.on("will-navigate", (event, url) => {
    if (isAllowedUrl(url)) {
      return;
    }

    event.preventDefault();
    void shell.openExternal(url);
  });
}

function configurePermissionHandlers(targetSession) {
  if (sessionSecurityConfigured) {
    return;
  }

  sessionSecurityConfigured = true;

  targetSession.setPermissionRequestHandler(
    (webContents, permission, callback, details) => {
      if (permission !== "notifications") {
        callback(false);
        return;
      }

      const requestingUrl = details?.requestingUrl || webContents.getURL();
      callback(isAllowedUrl(requestingUrl));
    },
  );

  targetSession.setPermissionCheckHandler(
    (_webContents, permission, requestingOrigin) => {
      if (permission !== "notifications") {
        return false;
      }

      return normalizeOrigin(requestingOrigin) === allowedOrigin;
    },
  );
}

function showMainWindow() {
  const windowRef = createWindow();

  if (windowRef.isMinimized()) {
    windowRef.restore();
  }

  if (!windowRef.isVisible()) {
    windowRef.show();
  }

  windowRef.focus();
}

function isMainWindowForeground() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return false;
  }

  return (
    mainWindow.isVisible() &&
    mainWindow.isFocused() &&
    !mainWindow.isMinimized()
  );
}

function sendReminderOpen(reminderId) {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  mainWindow.webContents.send("desktop:reminder-open", {
    reminderId: reminderId || null,
    route: "/reminders",
  });
}

function setDockBadge(rawCount) {
  const count = toNonNegativeInt(rawCount);

  if (typeof app.setBadgeCount === "function") {
    app.setBadgeCount(count);
  }

  if (
    process.platform === "darwin" &&
    app.dock &&
    typeof app.dock.setBadge === "function"
  ) {
    app.dock.setBadge(count > 0 ? String(count) : "");
  }
}

function setUnreadCount(rawCount) {
  unreadCount = toNonNegativeInt(rawCount);

  if (trayService) {
    trayService.setUnreadCount(unreadCount);
  }

  setDockBadge(unreadCount);

  if (process.platform === "win32" && mainWindow && !mainWindow.isDestroyed()) {
    if (unreadCount > 0) {
      const overlayIcon = trayService?.getOverlayIcon();
      if (overlayIcon) {
        mainWindow.setOverlayIcon(
          overlayIcon,
          `${unreadCount} unread reminders`,
        );
      }
      return;
    }

    mainWindow.setOverlayIcon(null, "No unread reminders");
  }
}

function setUnreadCountFromRenderer(rawCount) {
  const normalized = toNonNegativeInt(rawCount);
  lastRendererUnreadSyncAt = Date.now();
  lastRendererUnreadCount = normalized;
  setUnreadCount(normalized);
}

function applyPolledUnreadCount(rawCount) {
  const normalized = toNonNegativeInt(rawCount);
  const hasRecentRendererSync =
    Date.now() - lastRendererUnreadSyncAt <= RENDERER_UNREAD_SYNC_TTL_MS;

  // Prefer renderer-originated updates briefly to avoid stale poll responses
  // overriding an immediate "read" action just performed in-app.
  if (hasRecentRendererSync && normalized !== lastRendererUnreadCount) {
    log(
      "debug",
      `Reminder poll unread count ignored due to recent renderer sync. polled=${normalized} renderer=${lastRendererUnreadCount}`,
    );
    return;
  }

  setUnreadCount(normalized);
}

async function syncAuthTokenFromRenderer() {
  if (!reminderPoller || !mainWindow || mainWindow.isDestroyed()) {
    return;
  }

  try {
    const token = await mainWindow.webContents.executeJavaScript(
      `(function () {
        try {
          const value = localStorage.getItem('auth_token');
          return typeof value === 'string' ? value : '';
        } catch {
          return '';
        }
      })();`,
      true,
    );

    const normalized =
      typeof token === "string" && token.trim() ? token.trim() : null;
    reminderPoller.setAuthToken(normalized);
  } catch (error) {
    log("debug", `Unable to sync auth token from renderer: ${String(error)}`);
  }
}

function getMainWindowSessionFetcher() {
  if (mainWindow && !mainWindow.isDestroyed()) {
    const sessionRef = mainWindow.webContents?.session;
    if (sessionRef && typeof sessionRef.fetch === "function") {
      return (url, init) => sessionRef.fetch(url, init);
    }
  }

  if (typeof fetch === "function") {
    return (url, init) => fetch(url, init);
  }

  return () => {
    throw new Error(
      "No fetch implementation available in desktop main process.",
    );
  };
}

function getLaunchAtLogin() {
  if (process.platform !== "darwin" && process.platform !== "win32") {
    return false;
  }

  try {
    if (process.platform === "win32") {
      return Boolean(
        app.getLoginItemSettings({ path: process.execPath, args: [] })
          .openAtLogin,
      );
    }

    return Boolean(app.getLoginItemSettings().openAtLogin);
  } catch {
    return false;
  }
}

function setLaunchAtLogin(enabled) {
  if (process.platform !== "darwin" && process.platform !== "win32") {
    return false;
  }

  const shouldEnable = Boolean(enabled);

  try {
    if (process.platform === "win32") {
      app.setLoginItemSettings({
        openAtLogin: shouldEnable,
        path: process.execPath,
        args: [],
      });
    } else {
      app.setLoginItemSettings({ openAtLogin: shouldEnable });
    }
  } catch (error) {
    log("warn", `Unable to update launch-at-login setting: ${String(error)}`);
  }

  return getLaunchAtLogin();
}

function isDesktopAutoUpdateEnabled() {
  if (!autoUpdater) {
    return false;
  }

  if (process.platform !== "darwin" && process.platform !== "win32") {
    return false;
  }

  if (!app.isPackaged) {
    return false;
  }

  const rawDisabled = String(
    process.env.DESKTOP_AUTO_UPDATE_DISABLED || "",
  ).trim();
  return rawDisabled !== "1" && rawDisabled.toLowerCase() !== "true";
}

function isWindowsSquirrelFirstRun() {
  if (process.platform !== "win32") {
    return false;
  }

  return process.argv.some(
    (arg) => String(arg).toLowerCase() === "--squirrel-firstrun",
  );
}

function getDialogParentWindow() {
  if (!mainWindow || mainWindow.isDestroyed()) {
    return null;
  }

  return mainWindow;
}

function showDesktopMessageBox(options) {
  const parentWindow = getDialogParentWindow();
  if (parentWindow) {
    return dialog.showMessageBox(parentWindow, options);
  }

  return dialog.showMessageBox(options);
}

async function promptDownloadUpdate(info) {
  if (updatePromptInProgress) {
    return false;
  }

  updatePromptInProgress = true;
  try {
    const version = String(info?.version || "").trim() || "new";
    const result = await showDesktopMessageBox({
      type: "info",
      title: "Update Available",
      message: `Version ${version} is available.`,
      detail:
        "Do you want to download and install it now? You can also postpone and keep using the current version.",
      buttons: ["Download Update", "Later"],
      defaultId: 0,
      cancelId: 1,
      noLink: true,
    });

    return result.response === 0;
  } catch (error) {
    log("warn", `Update download prompt failed: ${String(error)}`);
    return false;
  } finally {
    updatePromptInProgress = false;
  }
}

async function promptInstallUpdate(info) {
  if (updatePromptInProgress) {
    return false;
  }

  updatePromptInProgress = true;
  try {
    const version = String(info?.version || "").trim() || "new";
    const result = await showDesktopMessageBox({
      type: "info",
      title: "Update Ready",
      message: `Version ${version} has been downloaded.`,
      detail:
        "Restart now to install the update, or choose Later and install when you quit the app.",
      buttons: ["Restart Now", "Later"],
      defaultId: 0,
      cancelId: 1,
      noLink: true,
    });

    return result.response === 0;
  } catch (error) {
    log("warn", `Update install prompt failed: ${String(error)}`);
    return false;
  } finally {
    updatePromptInProgress = false;
  }
}

function installDownloadedUpdateNow() {
  if (!autoUpdater) {
    return;
  }

  updateInstallInProgress = true;
  isQuitting = true;
  stopAutoUpdateScheduler();
  reminderPoller?.stop();

  // In update-install mode we don't want close-to-tray behavior to keep the
  // process alive. Force-close the main window if it still exists.
  if (mainWindow && !mainWindow.isDestroyed()) {
    mainWindow.removeAllListeners("close");
    try {
      mainWindow.close();
    } catch {
      // Best effort.
    }
  }

  try {
    // Use defaults for cross-platform compatibility.
    autoUpdater.quitAndInstall();
  } catch (error) {
    log("warn", `quitAndInstall failed, forcing relaunch fallback: ${String(error)}`);
    app.relaunch();
    app.exit(0);
    return;
  }

  // Safety net: if updater does not terminate process in a few seconds,
  // force a relaunch to avoid leaving users stuck after pressing Restart.
  setTimeout(() => {
    if (!updateInstallInProgress) {
      return;
    }

    log("warn", "Updater restart timeout reached, forcing app relaunch");
    app.relaunch();
    app.exit(0);
  }, 5000).unref();
}

function registerAutoUpdaterEventHandlers() {
  if (!autoUpdater) {
    return;
  }

  autoUpdater.removeAllListeners("checking-for-update");
  autoUpdater.removeAllListeners("update-available");
  autoUpdater.removeAllListeners("update-not-available");
  autoUpdater.removeAllListeners("download-progress");
  autoUpdater.removeAllListeners("update-downloaded");
  autoUpdater.removeAllListeners("before-quit-for-update");
  autoUpdater.removeAllListeners("error");

  autoUpdater.autoDownload = false;
  autoUpdater.autoInstallOnAppQuit = true;

  autoUpdater.on("checking-for-update", () => {
    log("info", "Checking for desktop updates");
  });

  autoUpdater.on("update-available", async (info) => {
    if (updateDownloadInProgress) {
      return;
    }

    log("info", "Desktop update available", { version: info?.version || null });
    const shouldDownload = await promptDownloadUpdate(info);
    if (!shouldDownload) {
      log("info", "Desktop update download postponed by user");
      return;
    }

    try {
      updateDownloadInProgress = true;
      await autoUpdater.downloadUpdate();
    } catch (error) {
      updateDownloadInProgress = false;
      log("error", `Desktop update download failed: ${String(error)}`);
    }
  });

  autoUpdater.on("update-not-available", () => {
    log("debug", "No desktop update available");
  });

  autoUpdater.on("download-progress", (progress) => {
    const percent = Number(progress?.percent || 0).toFixed(1);
    log("info", `Desktop update download progress: ${percent}%`);
  });

  autoUpdater.on("update-downloaded", async (info) => {
    updateDownloadInProgress = false;
    log("info", "Desktop update downloaded", { version: info?.version || null });

    const shouldInstallNow = await promptInstallUpdate(info);
    if (!shouldInstallNow) {
      log("info", "Desktop update install postponed by user");
      return;
    }

    installDownloadedUpdateNow();
  });

  autoUpdater.on("before-quit-for-update", () => {
    updateInstallInProgress = true;
    isQuitting = true;
    stopAutoUpdateScheduler();
    reminderPoller?.stop();
  });

  autoUpdater.on("error", (error) => {
    updateDownloadInProgress = false;
    log("error", `Desktop updater error: ${String(error)}`);
  });
}

async function checkForDesktopUpdates(trigger) {
  if (!autoUpdater) {
    return;
  }

  if (!isDesktopAutoUpdateEnabled()) {
    return;
  }

  if (isWindowsSquirrelFirstRun()) {
    log("info", "Skipping desktop update check during Windows first-run setup");
    return;
  }

  if (updateCheckInProgress) {
    log("debug", "Desktop update check skipped: check already in progress");
    return;
  }

  updateCheckInProgress = true;
  try {
    log("info", "Starting desktop update check", { trigger });
    await autoUpdater.checkForUpdates();
  } catch (error) {
    log("warn", `Desktop update check failed: ${String(error)}`);
  } finally {
    updateCheckInProgress = false;
  }
}

function startAutoUpdateScheduler() {
  if (!autoUpdater) {
    log(
      "warn",
      "Desktop auto-updates unavailable: electron-updater is not installed",
    );
    return;
  }

  if (!isDesktopAutoUpdateEnabled()) {
    log(
      "info",
      "Desktop auto-updates disabled for this run (platform, packaging, or env flag)",
    );
    return;
  }

  registerAutoUpdaterEventHandlers();

  setTimeout(() => {
    void checkForDesktopUpdates("startup");
  }, INITIAL_UPDATE_CHECK_DELAY_MS);

  updateCheckIntervalHandle = setInterval(() => {
    void checkForDesktopUpdates("interval");
  }, UPDATE_CHECK_INTERVAL_MS);
}

function stopAutoUpdateScheduler() {
  if (!updateCheckIntervalHandle) {
    return;
  }

  clearInterval(updateCheckIntervalHandle);
  updateCheckIntervalHandle = null;
}

function buildServices() {
  const iconsDir = path.join(__dirname, "assets", "icons");

  trayService = new TrayService({
    appName: APP_NAME,
    iconPath:
      process.platform === "darwin"
        ? path.join(iconsDir, "trayTemplate.png")
        : path.join(iconsDir, "tray.png"),
    unreadIconPath:
      process.platform === "darwin"
        ? path.join(iconsDir, "trayUnreadTemplate.png")
        : path.join(iconsDir, "tray-unread.png"),
    onOpen: () => showMainWindow(),
    onQuit: () => {
      isQuitting = true;
      app.quit();
    },
    onToggleLaunchAtLogin: (enabled) => setLaunchAtLogin(enabled),
    getLaunchAtLogin: () => getLaunchAtLogin(),
  });
  trayService.initialize();

  notificationService = new NotificationService({
    appName: APP_NAME,
    log: (level, message) => log(level, message),
    onClick: ({ reminderId }) => {
      if (reminderId) {
        void reminderPoller?.markReminderRead(reminderId, {
          deviceLabel: "Electron Desktop notification (click)",
        });
      }
      showMainWindow();
      sendReminderOpen(reminderId);
    },
    onClose: ({ reminderId }) => {
      if (!reminderId) {
        return;
      }

      void reminderPoller?.markReminderRead(reminderId, {
        deviceLabel: "Electron Desktop notification (close)",
      });
    },
  });

  reminderPoller = new ReminderFallbackPoller({
    baseUrl: allowedOrigin,
    intervalMs: reminderPollIntervalMs,
    request: getMainWindowSessionFetcher(),
    onUnreadCount: (count) => applyPolledUnreadCount(count),
    onReminder: async (reminder) => {
      if (isMainWindowForeground()) {
        log(
          "debug",
          `Reminder system notification skipped: main window is foreground. reminder_id=${reminder?.id}`,
        );
        return false;
      }

      return notificationService.showReminderNotification(reminder);
    },
    log: (level, message) => log(level, message),
  });
  reminderPoller.start();

  setUnreadCount(unreadCount);
}

function registerIpc() {
  ipcMain.removeAllListeners("desktop:auth-token");
  ipcMain.removeAllListeners("desktop:unread-count");
  ipcMain.removeAllListeners("desktop:push-receipt");
  ipcMain.removeAllListeners("desktop:push-reminder");
  ipcMain.removeHandler("desktop:launch-at-login:get");
  ipcMain.removeHandler("desktop:launch-at-login:set");

  ipcMain.on("desktop:auth-token", (_event, token) => {
    const normalized =
      typeof token === "string" && token.trim() ? token.trim() : null;
    reminderPoller.setAuthToken(normalized);

    if (!normalized) {
      setUnreadCount(0);
    }
  });

  ipcMain.on("desktop:unread-count", (_event, count) => {
    setUnreadCountFromRenderer(count);
  });

  ipcMain.on("desktop:push-receipt", (_event, reminderId) => {
    const normalized = toPositiveInt(reminderId);
    if (!normalized) {
      return;
    }

    reminderPoller.markReminderSeen(normalized);
  });

  ipcMain.on("desktop:push-reminder", (_event, payload) => {
    const normalized = normalizeDesktopPushReminder(payload);
    if (!normalized) {
      return;
    }

    if (isMainWindowForeground()) {
      log(
        "debug",
        `Desktop push reminder received while window is foreground. reminder_id=${normalized.id}`,
      );
      return;
    }

    const deliveredAsSystem =
      notificationService?.showReminderNotification(normalized);
    log(
      "debug",
      `Desktop push reminder notification evaluated. reminder_id=${normalized.id} delivered_system=${Boolean(deliveredAsSystem)}`,
    );
  });

  ipcMain.handle("desktop:launch-at-login:get", () => getLaunchAtLogin());

  ipcMain.handle("desktop:launch-at-login:set", (_event, enabled) => {
    const result = setLaunchAtLogin(Boolean(enabled));
    trayService?.refreshMenu();
    return result;
  });
}

if (gotSingleInstanceLock) {
  app.on("second-instance", () => {
    showMainWindow();
  });

  app.whenReady().then(() => {
    if (process.platform === "win32") {
      app.setAppUserModelId("com.revisbali.crm.desktop");
    }

    createWindow();
    buildServices();
    registerIpc();
    startAutoUpdateScheduler();
    void syncAuthTokenFromRenderer();

    log("info", "Desktop process started", {
      startUrl: startUrl.href,
      allowedOrigin,
      reminderPollIntervalMs,
    });
  });

  app.on("activate", () => {
    showMainWindow();
  });

  app.on("before-quit", () => {
    isQuitting = true;
    stopAutoUpdateScheduler();
    reminderPoller?.stop();
  });

  app.on("window-all-closed", () => {
    if (updateInstallInProgress) {
      app.quit();
      return;
    }

    // Keep the app running in tray (close-to-tray behavior).
  });

  app.on("quit", () => {
    updateInstallInProgress = false;
    stopAutoUpdateScheduler();
    trayService?.destroy();
    reminderPoller?.destroy();
  });
}
