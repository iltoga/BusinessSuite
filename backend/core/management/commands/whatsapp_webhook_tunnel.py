import json
import os
import re
import shutil
import signal
import subprocess
import time
from pathlib import Path
from typing import Any

import requests
from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

WEBHOOK_PATH = "/api/notifications/whatsapp/webhook/"
DEFAULT_STATE_FILE = "tmp/whatsapp_webhook_tunnel_state.json"
NGROK_URL_PATTERN = re.compile(r"url=(https://[^\s]+)")


class Command(BaseCommand):
    help = "Temporarily switch Meta WhatsApp webhook callback to a local ngrok tunnel and restore it later."

    def add_arguments(self, parser):
        parser.add_argument("action", choices=["start", "stop", "status"], help="Command action.")
        parser.add_argument(
            "--callback-url",
            dest="callback_url",
            default="",
            help="Optional public base URL. If omitted on start, ngrok is started automatically.",
        )
        parser.add_argument("--port", dest="port", type=int, default=8000, help="Local backend port for ngrok.")
        parser.add_argument(
            "--ngrok-bin",
            dest="ngrok_bin",
            default="ngrok",
            help="ngrok binary path or executable name.",
        )
        parser.add_argument(
            "--startup-timeout",
            dest="startup_timeout",
            type=int,
            default=30,
            help="Seconds to wait for ngrok URL detection.",
        )
        parser.add_argument(
            "--state-file",
            dest="state_file",
            default="",
            help=f"State file path (default: {DEFAULT_STATE_FILE}).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            dest="force",
            help="Overwrite an existing state file on start.",
        )
        parser.add_argument(
            "--skip-callback-check",
            action="store_true",
            dest="skip_callback_check",
            help="Skip public callback verification handshake before subscription update.",
        )
        parser.add_argument(
            "--keep-state",
            action="store_true",
            dest="keep_state",
            help="Keep state file after stop (for debugging/audit).",
        )

    def handle(self, *args, **options):
        action = options["action"]
        self.state_file = self._resolve_state_file(options.get("state_file") or "")
        self.graph_version = getattr(settings, "META_GRAPH_API_VERSION", "v23.0")
        self.app_id = str(getattr(settings, "META_APP_ID", "") or "").strip()
        self.app_secret = str(getattr(settings, "META_APP_SECRET", "") or "").strip()
        self.verify_token = str(getattr(settings, "META_TOKEN_CLIENT", "") or "").strip()

        if action == "start":
            self._handle_start(options)
            return
        if action == "stop":
            self._handle_stop(options)
            return
        self._handle_status()

    def _handle_start(self, options: dict[str, Any]) -> None:
        self._validate_required_settings()

        force = bool(options.get("force"))
        if self.state_file.exists() and not force:
            raise CommandError(
                f"State file already exists: {self.state_file}. Use --force or run stop first."
            )

        current_subscription = self._fetch_whatsapp_subscription()
        original_callback = current_subscription.get("callback_url") or ""
        fields = current_subscription.get("fields") or ["messages"]

        ngrok_pid = None
        ngrok_url = ""
        ngrok_log_file = ""
        callback_url_input = str(options.get("callback_url") or "").strip()
        if callback_url_input:
            callback_url = self._normalize_callback_url(callback_url_input)
        else:
            ngrok_url, ngrok_pid, ngrok_log_file = self._start_ngrok(
                ngrok_bin=str(options.get("ngrok_bin") or "ngrok"),
                port=int(options.get("port") or 8000),
                startup_timeout=int(options.get("startup_timeout") or 30),
            )
            callback_url = self._normalize_callback_url(ngrok_url)

        if not bool(options.get("skip_callback_check")):
            self._verify_callback_handshake(callback_url)

        try:
            self._update_whatsapp_subscription(callback_url=callback_url, fields=fields)
        except Exception:
            if ngrok_pid:
                self._terminate_process(ngrok_pid)
            raise

        state_payload = {
            "created_at": timezone.now().isoformat(),
            "old_callback_url": original_callback,
            "new_callback_url": callback_url,
            "fields": fields,
            "ngrok_pid": ngrok_pid,
            "ngrok_url": ngrok_url,
            "ngrok_log_file": ngrok_log_file,
            "graph_version": self.graph_version,
        }
        self._write_state(state_payload)

        self.stdout.write(self.style.SUCCESS("WhatsApp webhook temporary switch applied."))
        self.stdout.write(f"Old callback: {original_callback or '(empty)'}")
        self.stdout.write(f"New callback: {callback_url}")
        if ngrok_pid:
            self.stdout.write(f"ngrok pid: {ngrok_pid}")
        self.stdout.write(f"State file: {self.state_file}")
        self.stdout.write("Restore later with: python manage.py whatsapp_webhook_tunnel stop")

    def _handle_stop(self, options: dict[str, Any]) -> None:
        self._validate_required_settings()
        state = self._read_state()
        if not state:
            raise CommandError(f"State file not found or invalid: {self.state_file}")

        old_callback_url = str(state.get("old_callback_url") or "").strip()
        fields = list(state.get("fields") or [])
        if not old_callback_url:
            raise CommandError("State file does not contain old_callback_url.")
        if not fields:
            fields = ["messages"]

        self._update_whatsapp_subscription(callback_url=old_callback_url, fields=fields)

        ngrok_pid = state.get("ngrok_pid")
        if ngrok_pid:
            self._terminate_process(int(ngrok_pid))

        if bool(options.get("keep_state")):
            state["stopped_at"] = timezone.now().isoformat()
            self._write_state(state)
        else:
            self.state_file.unlink(missing_ok=True)

        self.stdout.write(self.style.SUCCESS("WhatsApp webhook callback restored."))
        self.stdout.write(f"Restored callback: {old_callback_url}")
        if ngrok_pid:
            self.stdout.write(f"Attempted ngrok terminate: pid {ngrok_pid}")

    def _handle_status(self) -> None:
        self._validate_required_settings()
        subscription = self._fetch_whatsapp_subscription()
        callback_url = str(subscription.get("callback_url") or "").strip()
        fields = subscription.get("fields") or []
        self.stdout.write("Current Meta webhook subscription:")
        self.stdout.write(f"Callback URL: {callback_url or '(empty)'}")
        self.stdout.write(f"Fields: {', '.join(fields) if fields else '(none)'}")

        state = self._read_state()
        if not state:
            self.stdout.write(f"No local state file: {self.state_file}")
            return
        self.stdout.write("Local temporary switch state:")
        self.stdout.write(json.dumps(state, indent=2))

    def _resolve_state_file(self, raw_path: str) -> Path:
        if raw_path:
            path = Path(raw_path)
            if not path.is_absolute():
                path = Path(getattr(settings, "ROOT_DIR", ".")) / path
        else:
            path = Path(getattr(settings, "ROOT_DIR", ".")) / DEFAULT_STATE_FILE
        return path

    def _validate_required_settings(self) -> None:
        missing = []
        if not self.app_id:
            missing.append("META_APP_ID")
        if not self.app_secret:
            missing.append("META_APP_SECRET")
        if not self.verify_token:
            missing.append("META_TOKEN_CLIENT")
        if missing:
            raise CommandError(f"Missing required settings: {', '.join(missing)}")

    def _app_access_token(self) -> str:
        return f"{self.app_id}|{self.app_secret}"

    def _subscription_endpoint(self) -> str:
        return f"https://graph.facebook.com/{self.graph_version}/{self.app_id}/subscriptions"

    def _fetch_whatsapp_subscription(self) -> dict[str, Any]:
        response = requests.get(
            self._subscription_endpoint(),
            params={"access_token": self._app_access_token()},
            timeout=20,
        )
        if response.status_code >= 400:
            raise CommandError(f"Failed to fetch app subscriptions ({response.status_code}): {response.text}")

        data = response.json().get("data") or []
        subscription = next((item for item in data if item.get("object") == "whatsapp_business_account"), None)
        if not subscription:
            raise CommandError("No 'whatsapp_business_account' subscription found for this app.")

        fields = [entry.get("name") for entry in (subscription.get("fields") or []) if entry.get("name")]
        return {
            "callback_url": str(subscription.get("callback_url") or "").strip(),
            "fields": fields or ["messages"],
        }

    def _update_whatsapp_subscription(self, *, callback_url: str, fields: list[str]) -> None:
        payload = {
            "access_token": self._app_access_token(),
            "object": "whatsapp_business_account",
            "callback_url": callback_url,
            "verify_token": self.verify_token,
            "fields": ",".join(fields),
        }
        response = requests.post(self._subscription_endpoint(), data=payload, timeout=20)
        if response.status_code >= 400:
            raise CommandError(f"Failed to update webhook subscription ({response.status_code}): {response.text}")

        try:
            body = response.json() if response.text else {}
        except ValueError:
            body = {}
        if isinstance(body, dict) and body.get("success") is False:
            raise CommandError(f"Webhook subscription update failed: {response.text}")

    def _normalize_callback_url(self, raw_url: str) -> str:
        value = str(raw_url or "").strip()
        if not value:
            raise CommandError("Callback URL is empty.")
        if not value.startswith(("http://", "https://")):
            value = f"https://{value}"
        value = value.rstrip("/")
        if value.endswith(WEBHOOK_PATH.rstrip("/")):
            return f"{value}/"
        return f"{value}{WEBHOOK_PATH}"

    def _verify_callback_handshake(self, callback_url: str) -> None:
        challenge = "webhook-check"
        response = requests.get(
            callback_url,
            params={
                "hub.mode": "subscribe",
                "hub.challenge": challenge,
                "hub.verify_token": self.verify_token,
            },
            timeout=20,
        )
        if response.status_code != 200:
            raise CommandError(
                f"Callback verification failed ({response.status_code}): {response.text[:300]}"
            )
        if challenge not in str(response.text):
            raise CommandError("Callback verification succeeded but challenge echo mismatch.")

    def _start_ngrok(self, *, ngrok_bin: str, port: int, startup_timeout: int) -> tuple[str, int, str]:
        binary = shutil.which(ngrok_bin) if os.path.sep not in ngrok_bin else ngrok_bin
        if not binary:
            raise CommandError(f"ngrok binary not found: {ngrok_bin}")

        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        log_file = self.state_file.parent / f"whatsapp_webhook_tunnel_ngrok_{int(time.time())}.log"
        command = [binary, "http", str(port), "--inspect=false", f"--log={log_file}"]
        process = subprocess.Popen(
            command,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )

        deadline = time.monotonic() + max(startup_timeout, 1)
        log_lines: list[str] = []
        while time.monotonic() < deadline:
            if process.poll() is not None:
                break
            if log_file.exists():
                text = log_file.read_text(errors="ignore")
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if lines:
                    log_lines = lines[-30:]
                    match = NGROK_URL_PATTERN.search(text)
                    if match:
                        tunnel_url = str(match.group(1)).strip()
                        if tunnel_url:
                            return tunnel_url, int(process.pid), str(log_file)
            time.sleep(0.2)

        self._terminate_process(int(process.pid))
        last_logs = "\n".join(log_lines[-10:])
        raise CommandError(
            "Failed to detect ngrok tunnel URL within timeout. "
            f"Last logs:\n{last_logs or '(no logs)'}"
        )

    def _terminate_process(self, pid: int) -> None:
        try:
            os.kill(pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except OSError as exc:
            raise CommandError(f"Unable to terminate process {pid}: {exc}") from exc

    def _read_state(self) -> dict[str, Any] | None:
        if not self.state_file.exists():
            return None
        try:
            payload = json.loads(self.state_file.read_text())
        except Exception:
            return None
        return payload if isinstance(payload, dict) else None

    def _write_state(self, payload: dict[str, Any]) -> None:
        self.state_file.parent.mkdir(parents=True, exist_ok=True)
        self.state_file.write_text(json.dumps(payload, indent=2))
