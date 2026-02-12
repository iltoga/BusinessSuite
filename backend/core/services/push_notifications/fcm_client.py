import json
import logging
from typing import Any

import requests
from django.conf import settings

try:
    from google.auth.transport.requests import Request
    from google.oauth2 import service_account
except Exception:  # pragma: no cover - environment dependent
    Request = None
    service_account = None

logger = logging.getLogger(__name__)

FCM_SCOPE = "https://www.googleapis.com/auth/firebase.messaging"
FCM_SEND_ENDPOINT = "https://fcm.googleapis.com/v1/projects/{project_id}/messages:send"


class FcmConfigurationError(RuntimeError):
    """Raised when FCM settings are missing or invalid."""


class FcmSendError(RuntimeError):
    """Raised when Firebase returns an error while sending a message."""

    def __init__(
        self,
        message: str,
        *,
        http_status: int | None = None,
        error_status: str | None = None,
        error_code: str | None = None,
        response_body: dict[str, Any] | None = None,
    ):
        super().__init__(message)
        self.http_status = http_status
        self.error_status = error_status
        self.error_code = error_code
        self.response_body = response_body or {}

    def is_token_invalid(self) -> bool:
        token_error_codes = {"UNREGISTERED", "INVALID_ARGUMENT"}
        return (self.error_code or "").upper() in token_error_codes


class FcmClient:
    """Minimal client for Firebase Cloud Messaging HTTP v1."""

    def __init__(self, service_account_file: str | None = None, project_id: str | None = None, timeout: int = 10):
        self.service_account_file = service_account_file or getattr(settings, "GOOGLE_FCM_SERVICE_ACCOUNT_FILE", "")
        self.project_id = project_id or getattr(settings, "FCM_PROJECT_ID", "")
        self.timeout = timeout

        if not self.service_account_file:
            raise FcmConfigurationError("GOOGLE_FCM_SERVICE_ACCOUNT_FILE is not configured")

        if service_account is None or Request is None:
            raise FcmConfigurationError("google-auth is not available for FCM service account authentication")

        try:
            self.credentials = service_account.Credentials.from_service_account_file(
                self.service_account_file,
                scopes=[FCM_SCOPE],
            )
        except Exception as exc:
            raise FcmConfigurationError(f"Failed to initialize FCM credentials: {exc}") from exc

        if not self.project_id:
            # `google.oauth2.service_account.Credentials` exposes project_id for service account json files.
            self.project_id = getattr(self.credentials, "project_id", "") or self._project_id_from_service_account_file()

        if not self.project_id:
            raise FcmConfigurationError(
                "FCM project id is missing. Set FCM_PROJECT_ID or use a service account file containing project_id."
            )

    def send_to_token(
        self,
        *,
        token: str,
        title: str,
        body: str,
        data: dict[str, Any] | None = None,
        link: str | None = None,
    ) -> dict[str, Any]:
        if not token:
            raise FcmSendError("FCM token is required")

        message: dict[str, Any] = {
            "token": token,
            "notification": {
                "title": title,
                "body": body,
            },
        }

        if data:
            # FCM data payload must be string-key/string-value pairs.
            message["data"] = {str(key): self._stringify_value(value) for key, value in data.items()}

        if link:
            message["webpush"] = {"fcm_options": {"link": link}}

        payload = {"message": message}
        endpoint = FCM_SEND_ENDPOINT.format(project_id=self.project_id)
        headers = {
            "Authorization": f"Bearer {self._access_token()}",
            "Content-Type": "application/json; charset=UTF-8",
        }

        response = requests.post(
            endpoint,
            headers=headers,
            data=json.dumps(payload),
            timeout=self.timeout,
        )

        if response.status_code >= 400:
            raise self._build_send_error(response)

        try:
            return response.json()
        except ValueError:
            return {"raw": response.text}

    def _access_token(self) -> str:
        if Request is None:
            raise FcmConfigurationError("google-auth Request is not available for FCM access token refresh")
        self.credentials.refresh(Request())
        if not self.credentials.token:
            raise FcmConfigurationError("Failed to refresh FCM access token")
        return str(self.credentials.token)

    def _project_id_from_service_account_file(self) -> str:
        try:
            with open(self.service_account_file, "r", encoding="utf-8") as handle:
                payload = json.load(handle)
        except Exception:
            return ""
        return str(payload.get("project_id") or "").strip()

    def _build_send_error(self, response: requests.Response) -> FcmSendError:
        parsed: dict[str, Any]
        try:
            parsed = response.json()
        except ValueError:
            parsed = {"error": {"message": response.text}}

        error = parsed.get("error", {})
        message = error.get("message") or f"FCM send failed with status {response.status_code}"
        status = error.get("status")
        error_code = self._extract_fcm_error_code(error)
        return FcmSendError(
            str(message),
            http_status=response.status_code,
            error_status=status,
            error_code=error_code,
            response_body=parsed,
        )

    @staticmethod
    def _extract_fcm_error_code(error: dict[str, Any]) -> str | None:
        details = error.get("details") or []
        if not isinstance(details, list):
            return None
        for detail in details:
            if not isinstance(detail, dict):
                continue
            code = detail.get("errorCode")
            if isinstance(code, str) and code:
                return code
        return None

    @staticmethod
    def _stringify_value(value: Any) -> str:
        if value is None:
            return ""
        if isinstance(value, (dict, list)):
            return json.dumps(value, separators=(",", ":"))
        return str(value)
