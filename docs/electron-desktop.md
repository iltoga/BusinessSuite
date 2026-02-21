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
  - `DESKTOP_START_URL=http://localhost:4200`

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
5. Desktop system notifications expose quick actions:
   - `Mark as Read`: calls `/api/calendar-reminders/inbox/mark-read/` for that reminder.
   - `Snooze 15m`: calls `/api/calendar-reminders/inbox/snooze/` and reschedules the reminder.

## Tray and Badge Behavior

- Close window hides app to tray (does not quit).
- Tray menu:
  - Open CRM
  - Check for Updates
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
  - then every 1 hour
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
- `latest*.yml` metadata includes SHA-512 checksums for installer files; Electron verifies these during update download/install.

Desktop updates are published automatically by
`.github/workflows/desktop-installers.yml` on pushes to `main` that touch `desktop/**`
(or via manual workflow dispatch).

- CI stamps desktop version as `0.1.<workflow_run_number>` so installed apps can detect a newer version.
- CI uploads update feed files directly to `${DATA_PATH}/desktop-updates` on VPS.
- Nginx location `/desktop-updates/*` serves files from `/var/www/desktop-updates`.

This means frontend-only merges do not publish desktop update metadata/artifacts, so
installed desktop apps are prompted only when a new desktop build is published.

## Generate New Desktop Installers

Use one of the following release paths.

### Method A (Recommended): GitHub CI auto-build + publish

This is the standard path for production desktop releases.

1. Make your desktop changes under `desktop/**` (for example `desktop/main.js`, `desktop/electron-builder.yml`).
2. Merge to `main`.
3. GitHub Actions runs `.github/workflows/desktop-installers.yml` automatically.
4. The workflow builds:
   - macOS installer artifacts (`.dmg`, `.zip`, `latest-mac.yml`, `.blockmap`)
   - Windows installer artifacts (`.exe`, `latest.yml`, `.blockmap`)
5. The workflow publishes the merged update feed to `${DATA_PATH}/desktop-updates` on VPS.
6. Installed apps check the feed hourly and prompt users when a newer desktop release is available.

Notes:

- Frontend-only merges do not trigger this workflow.
- CI stamps desktop version as `0.1.<github.run_number>`.
- Use this flow only when you intentionally want to publish a desktop release.

### Method B: GitHub CI manual dispatch (no new commit needed)

Use this when you need to rebuild/publish installers from current `main` without pushing a new commit.

1. Open GitHub -> Actions -> `desktop-installers`.
2. Click `Run workflow` (workflow_dispatch).
3. Wait for `build-mac`, `build-win`, and `publish-update-feed` jobs to succeed.
4. Verify that `${DATA_PATH}/desktop-updates` contains fresh `latest.yml` and `latest-mac.yml`.

### Method C: Local build (manual artifacts)

Use this for local QA or ad-hoc installer generation.

```bash
cd desktop
bun install
bun run dist:mac
bun run dist:win
```

Artifacts are written to `desktop/dist/`.

Important:

- Local builds do not publish to the remote auto-update feed by default.
- If you manually upload local artifacts to the feed path, ensure `latest.yml` and `latest-mac.yml` match the uploaded binaries (checksums must be consistent).

### Release verification checklist

After any release method, verify:

1. `latest.yml` and `latest-mac.yml` exist in `${DATA_PATH}/desktop-updates`.
2. Referenced installer files (`.exe`, `.zip`) exist at the same feed location.
3. A packaged desktop app detects the update, asks download/install, and can restart via `quitAndInstall()`.

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
bun run dev
```

Windows PowerShell equivalent:

```powershell
cd desktop
$env:DESKTOP_START_URL = "http://localhost:4200"
bun run start
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
