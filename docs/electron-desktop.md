# Electron Desktop (RevisBaliCRM)

This document describes the Electron desktop wrapper for the existing Angular + Django deployment.

## Goals

- Keep current VPS web deployment unchanged.
- Run CRM as a native desktop app (macOS + Windows).
- Support close-to-tray behavior.
- Show system notifications for reminders when the window is closed to tray.
- Support remote auto-updates for macOS and Windows installs.
- Keep frontend/backend communication same-origin to avoid CORS reconfiguration.

## Repository Layout

Desktop runtime is isolated under:

- `desktop/main.js`
- `desktop/preload.js`
- `desktop/services/tray-service.js`
- `desktop/services/notification-service.js`
- `desktop/services/reminder-fallback-poller.js`
- `desktop/electron-builder.yml`

Frontend integration points:

- `frontend/src/app/core/services/desktop-bridge.service.ts`
- `frontend/src/app/core/services/auth.service.ts`
- `frontend/src/app/core/services/reminder-inbox.service.ts`
- `frontend/src/app/core/services/push-notifications.service.ts`
- `frontend/src/app/app.ts`

## Runtime Modes

- Production default:
  - `DESKTOP_START_URL=https://crm.revisbali.com`
- Local development example:
  - `DESKTOP_START_URL=http://127.0.0.1:4200`

`DESKTOP_ALLOWED_ORIGIN` can be set explicitly. If omitted, it uses `DESKTOP_START_URL` origin.

## Security Defaults

Electron `BrowserWindow` is configured with:

- `nodeIntegration: false`
- `contextIsolation: true`
- `sandbox: true`
- `webSecurity: true`

Additionally:

- Navigation is restricted to the configured origin.
- External URLs are opened in the OS browser.
- Notifications permission is only granted for allowed origin.

## Notifications Strategy

1. Primary path: existing web push/FCM flow in Angular renderer.
2. Fallback path: Electron main-process poller calls `/api/calendar-reminders/inbox/` every 60s.
3. Deduplication:
   - Renderer publishes reminder receipts to main process.
   - Poller keeps a seen-reminder cache.
4. When fallback notification is shown, main process calls `/api/calendar-reminders/{id}/ack/` with `channel=system`.

## Tray and Badge Behavior

- Close window hides app to tray (does not quit).
- Tray menu:
  - Open CRM
  - Launch at Login toggle (macOS/Windows)
  - Quit
- Badge/indicator:
  - `app.setBadgeCount` for dock/taskbar badge where supported.
  - Windows overlay icon when unread reminders exist.
  - Tray tooltip and menu unread count.

## Auto Updates (macOS + Windows)

Desktop auto-update is implemented in Electron main process with `electron-updater`.

- Update checks run automatically on packaged builds:
  - once shortly after startup
  - then every 4 hours
- On update detection:
  - app asks user to download now or later
  - if accepted, download starts immediately
  - after download, app asks restart now or later
  - if user picks restart now, app calls `quitAndInstall()` and restarts automatically
  - if user picks later, update installs on next full app quit

Current update feed is configured in `desktop/electron-builder.yml`:

- `publish.provider = generic`
- `publish.url = https://crm.revisbali.com/desktop-updates`
- Nginx serves this route directly from `/var/www/desktop-updates`.

Required published files per release include:

- Windows: `latest.yml` + `.exe` package artifacts
- macOS: `latest-mac.yml` + `.zip` (and `.dmg` for manual install)

Desktop updates are published automatically by
`.github/workflows/desktop-installers.yml` on every push to `main`.

- CI stamps desktop version as `0.1.<workflow_run_number>` so installed apps can detect a newer version.
- CI uploads update feed files directly to `${DATA_PATH}/desktop-updates` on VPS.
- Nginx location `/desktop-updates/*` serves files from `/var/www/desktop-updates`.

## Commands (Bun)

```bash
cd desktop
bun install
bun run dev
bun run dist:mac
bun run dist:win
```

Optional desktop env setup:

```bash
cd desktop
cp .env.example .env
```

Environment variables are:

- `DESKTOP_START_URL`
- `DESKTOP_ALLOWED_ORIGIN`
- `DESKTOP_LOG_LEVEL`
- `DESKTOP_REMINDER_POLL_INTERVAL_MS` (fallback poll interval; default `15000`)
- `DESKTOP_AUTO_UPDATE_DISABLED` (`1`/`true` disables auto-update checks in packaged builds)

After changing `desktop/.env`, fully quit the running tray app and start it again.
The desktop app is single-instance; launching a second instance reuses the already-running process.

Local frontend for desktop testing:

```bash
cd frontend
bun run start
```

Then run desktop with local URL:

```bash
cd desktop
DESKTOP_START_URL=http://127.0.0.1:4200 bun run dev
```

Windows PowerShell equivalent:

```powershell
cd desktop
$env:DESKTOP_START_URL = "http://127.0.0.1:4200"
bun run dev
```

## Installer Notes

- macOS targets: `dmg` + `zip` (zip is required for auto-update metadata)
- Windows target: `nsis`
- Production auto-updates should use signed installers:
  - macOS requires Developer ID signing (and notarization recommended)
  - Windows signing is strongly recommended to reduce SmartScreen friction and update trust issues

CI workflow: `.github/workflows/desktop-installers.yml`

Required secrets for desktop feed publishing:

- `VPS_HOST`
- `VPS_USERNAME`
- `SSH_PRIVATE_KEY`
- `REPO_DIR`

If your existing `deploy.yml` workflow is already working, these secrets are already present.
No additional desktop-specific secret or env variable is required.
