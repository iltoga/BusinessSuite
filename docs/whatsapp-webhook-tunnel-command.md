# WhatsApp Webhook Tunnel Command

This document explains how to use the Django management command that temporarily switches the Meta WhatsApp webhook callback URL to a local/public tunnel endpoint for local testing.

Command name:

```bash
python backend/manage.py whatsapp_webhook_tunnel <action> [options]
```

Actions:

- `start`: switch callback to a tunnel URL (auto-start ngrok by default)
- `stop`: restore the original callback URL and stop ngrok (if started by command)
- `status`: print current Meta subscription callback and local command state

## Why this exists

WhatsApp message delivery status updates (`sent`, `delivered`, `read`) come from Meta webhooks.

If your backend uses a local database, but Meta sends webhooks to a production callback URL, local `workflow_notification` records stay `pending`.

This command solves that for local debugging by temporarily repointing webhook delivery to your local environment via ngrok.

## Prerequisites

Required environment variables in backend settings:

- `META_APP_ID`
- `META_APP_SECRET`
- `META_TOKEN_CLIENT`
- `META_GRAPH_API_VERSION` (optional, defaults in settings)

Recommended:

- Running local backend on port `8000`
- `ngrok` installed and authenticated locally

The command updates Meta app subscriptions through:

- `/{META_APP_ID}/subscriptions`
- object: `whatsapp_business_account`

## Safety model

`start` saves a state backup file before/after switching:

- Default state file: `backend/tmp/whatsapp_webhook_tunnel_state.json`
- Stored values include:
  - previous callback URL
  - new callback URL
  - subscribed fields
  - ngrok PID (if command started ngrok)

`stop` restores callback URL from that state file.

## Quick start (recommended flow)

From project root:

```bash
cd backend
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel start
```

Check status:

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel status
```

Run your WhatsApp send tests. When done:

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel stop
```

## Command options

Common options:

- `--state-file <path>`
- `--force` (for `start`, overwrite existing state file)
- `--keep-state` (for `stop`, keep state file for audit/debug)

`start` options:

- `--callback-url <public-url>`
- `--port <int>` (default `8000`)
- `--ngrok-bin <path-or-name>` (default `ngrok`)
- `--startup-timeout <seconds>` (default `30`)
- `--skip-callback-check` (skip `hub.challenge` verification before switching)

## Examples

### 1) Start with auto ngrok

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel start
```

What happens:

1. Fetch current Meta webhook subscription for `whatsapp_business_account`
2. Start ngrok tunnel to local port (`8000` by default)
3. Verify callback URL handshake (`hub.mode=subscribe`, token check)
4. Update Meta callback URL
5. Save state file

### 2) Start with an already-running tunnel URL

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel start \
  --callback-url https://your-public-url.ngrok-free.app
```

Useful when ngrok is managed outside this command.

### 3) Check current state and callback

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel status
```

Output includes:

- current callback URL on Meta subscription
- subscribed webhook fields
- local state file content (if present)

### 4) Restore callback and stop tunnel

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel stop
```

### 5) Restore but keep state file

```bash
DJANGO_SETTINGS_MODULE=business_suite.settings.dev uv run python manage.py whatsapp_webhook_tunnel stop --keep-state
```

## Troubleshooting

### `State file already exists`

Cause:

- previous `start` was not followed by `stop`

Fix:

1. run `... whatsapp_webhook_tunnel stop`
2. or run `start --force`

### `ngrok binary not found`

Cause:

- `ngrok` is not installed or not in PATH

Fix:

1. install ngrok
2. pass explicit path: `--ngrok-bin /full/path/to/ngrok`

### `Failed to detect ngrok tunnel URL within timeout`

Cause:

- ngrok failed to start or did not provide URL in time

Fix:

1. increase timeout: `--startup-timeout 60`
2. check local ngrok auth/config
3. run with explicit `--callback-url`

### Callback verification failure

Cause:

- public URL cannot reach local backend
- `META_TOKEN_CLIENT` mismatch
- backend endpoint unavailable

Fix:

1. confirm local endpoint:
   - `GET /api/notifications/whatsapp/webhook/?hub.mode=subscribe&hub.challenge=x&hub.verify_token=<META_TOKEN_CLIENT>`
2. confirm backend is running on selected port
3. confirm tunnel forwards to same backend port

### Meta API errors (`190`, `463`, etc.)

Cause:

- expired/invalid token

Fix:

1. refresh WhatsApp Cloud API token
2. restart backend processes if token loaded from `.env`

## Operational notes

- This command changes a shared Meta app callback URL.
- During local testing, production webhook traffic for this app will be redirected to your local tunnel.
- Always run `stop` after testing to restore the original callback.

## Related code

- Command: `backend/core/management/commands/whatsapp_webhook_tunnel.py`
- Webhook endpoint: `backend/api/views.py` (`whatsapp_webhook`)
- Status processing: `backend/notifications/services/providers.py` (`process_whatsapp_webhook_payload`)

