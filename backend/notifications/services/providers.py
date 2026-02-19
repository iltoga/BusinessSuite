import hashlib
import hmac
import logging
import re
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Any, Mapping

import requests
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.utils import timezone

from notifications.services.meta_access_token import get_meta_whatsapp_access_token

logger = logging.getLogger(__name__)

WHATSAPP_META_STATUS_SENT = "sent"
WHATSAPP_META_STATUS_DELIVERED = "delivered"
WHATSAPP_META_STATUS_READ = "read"
WHATSAPP_META_STATUS_FAILED = "failed"

_WHATSAPP_PROGRESS_RANK = {
    "pending": 0,
    "sent": 1,
    "delivered": 2,
    "read": 3,
}


class MetaWhatsAppStatusLookupUnsupported(RuntimeError):
    """Raised when message-level status lookup is not supported by Graph API."""


class NotificationProvider(ABC):
    channel: str

    @abstractmethod
    def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> str:
        raise NotImplementedError


class EmailNotificationProvider(NotificationProvider):
    channel = "email"

    def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> str:
        sender = getattr(settings, "NOTIFICATION_FROM_EMAIL", "dewi@revisbali.com")
        message = EmailMultiAlternatives(subject=subject, body=body, from_email=sender, to=[recipient])
        if html_body:
            message.attach_alternative(html_body, "text/html")
        count = message.send(fail_silently=False)
        return f"sent:{count}"


class WhatsappNotificationProvider(NotificationProvider):
    """WhatsApp transport using Meta WhatsApp Cloud API.

    Required settings:
    - META_WHATSAPP_ACCESS_TOKEN
    - META_PHONE_NUMBER_ID (or META_WHATSAPP_BUSINESS_NUMBER_ID)
    Optional:
    - META_GRAPH_API_VERSION (default: v23.0)
    """

    channel = "whatsapp"

    def send(
        self,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
        *,
        prefer_template: bool | None = None,
        allow_template_fallback: bool | None = None,
    ) -> str:
        access_token = get_meta_whatsapp_access_token()
        phone_number_id = getattr(settings, "META_PHONE_NUMBER_ID", "") or getattr(
            settings, "META_WHATSAPP_BUSINESS_NUMBER_ID", ""
        )
        graph_version = getattr(settings, "META_GRAPH_API_VERSION", "v23.0")

        if not access_token or not phone_number_id:
            logger.info("Meta WhatsApp credentials are not configured. Returning queued placeholder.")
            return f"queued_whatsapp:{recipient}"

        url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"
        prefer_template_value = (
            bool(getattr(settings, "META_WHATSAPP_PREFER_TEMPLATE", False))
            if prefer_template is None
            else bool(prefer_template)
        )
        allow_template_fallback_value = (
            bool(getattr(settings, "META_WHATSAPP_ALLOW_TEMPLATE_FALLBACK", False))
            if allow_template_fallback is None
            else bool(allow_template_fallback)
        )
        template_only = bool(getattr(settings, "META_WHATSAPP_TEMPLATE_ONLY", False))
        if prefer_template_value:
            try:
                return self._send_template_message(url=url, recipient=recipient)
            except Exception as exc:
                if template_only or not allow_template_fallback_value:
                    raise
                logger.warning(
                    "WhatsApp template send failed; falling back to text. recipient=%s error_type=%s error=%s",
                    recipient,
                    type(exc).__name__,
                    str(exc),
                )

        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._normalize_meta_phone_number(recipient),
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body,
            },
        }

        response = self._post_graph_json(url=url, payload=payload, access_token=access_token)
        if response.status_code >= 400:
            code = _extract_meta_error_code(response)
            # Free-form text can be blocked outside the customer service window.
            # Retry with an approved template in this case (common with test/sandbox setups).
            if allow_template_fallback_value and code in {131047, 470}:
                return self._send_template_message(
                    url=url,
                    recipient=recipient,
                )
            raise RuntimeError(f"WhatsApp send failed ({response.status_code}): {response.text}")

        data = response.json()
        messages = data.get("messages") or []
        message_id = messages[0].get("id") if messages else None
        if not message_id:
            raise RuntimeError("WhatsApp send succeeded but no message id returned by Meta.")
        return str(message_id)

    def _normalize_meta_phone_number(self, value: str) -> str:
        raw = (value or "").strip()
        if raw.startswith("whatsapp:"):
            raw = raw.split(":", 1)[1]
        return re.sub(r"[^\d]", "", raw)

    def _send_template_message(self, *, url: str, recipient: str) -> str:
        template_name = getattr(settings, "META_WHATSAPP_DEFAULT_TEMPLATE_NAME", "hello_world")
        language_code = getattr(settings, "META_WHATSAPP_DEFAULT_TEMPLATE_LANG", "en_US")
        payload = {
            "messaging_product": "whatsapp",
            "recipient_type": "individual",
            "to": self._normalize_meta_phone_number(recipient),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        response = self._post_graph_json(url=url, payload=payload)
        if response.status_code >= 400:
            raise RuntimeError(f"WhatsApp template send failed ({response.status_code}): {response.text}")

        data = response.json()
        messages = data.get("messages") or []
        message_id = messages[0].get("id") if messages else None
        if not message_id:
            raise RuntimeError("WhatsApp template send succeeded but no message id returned by Meta.")
        return str(message_id)

    def get_message_status(self, *, message_id: str) -> dict[str, Any]:
        """Best-effort Graph lookup for outbound WhatsApp message state."""
        access_token = get_meta_whatsapp_access_token()
        graph_version = getattr(settings, "META_GRAPH_API_VERSION", "v23.0")
        if not access_token:
            raise RuntimeError("Meta WhatsApp access token is not configured.")

        normalized_message_id = str(message_id or "").strip()
        if not normalized_message_id:
            raise RuntimeError("Message id is required to poll Meta status.")

        url = f"https://graph.facebook.com/{graph_version}/{normalized_message_id}"
        response = self._get_graph_json(
            url,
            params={"fields": "status,message_status,errors,statuses"},
            access_token=access_token,
        )
        if response.status_code >= 400:
            error_info = _extract_meta_error_info(response)
            code = error_info.get("code")
            subcode = error_info.get("error_subcode")
            if response.status_code == 400 and code == 100 and subcode == 33:
                raise MetaWhatsAppStatusLookupUnsupported(
                    "Meta does not support direct status lookup by message id for this object."
                )
            raise RuntimeError(f"WhatsApp status poll failed ({response.status_code}): {response.text}")

        data = response.json() or {}
        status = _extract_meta_status_from_response(data)
        if not status:
            raise RuntimeError(f"WhatsApp status poll returned no status for message id {normalized_message_id}.")
        return {"status": status, "raw": data}

    def _post_graph_json(self, *, url: str, payload: Mapping[str, Any], access_token: str | None = None):
        token = str(access_token or get_meta_whatsapp_access_token()).strip()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if _response_has_expired_token_error(response):
            refreshed = get_meta_whatsapp_access_token(force_refresh=True)
            if refreshed:
                retry_headers = {
                    "Authorization": f"Bearer {refreshed}",
                    "Content-Type": "application/json",
                }
                response = requests.post(url, json=payload, headers=retry_headers, timeout=20)
        return response

    def _get_graph_json(
        self,
        url: str,
        *,
        params: Mapping[str, Any] | None = None,
        access_token: str | None = None,
    ):
        token = str(access_token or get_meta_whatsapp_access_token()).strip()
        headers = {"Authorization": f"Bearer {token}"}
        response = requests.get(url, params=params or {}, headers=headers, timeout=20)
        if _response_has_expired_token_error(response):
            refreshed = get_meta_whatsapp_access_token(force_refresh=True)
            if refreshed:
                retry_headers = {"Authorization": f"Bearer {refreshed}"}
                response = requests.get(url, params=params or {}, headers=retry_headers, timeout=20)
        return response


class NotificationDispatcher:
    def __init__(self):
        self.providers = {"email": EmailNotificationProvider(), "whatsapp": WhatsappNotificationProvider()}

    def send(
        self,
        channel: str,
        recipient: str,
        subject: str,
        body: str,
        html_body: str | None = None,
    ) -> str:
        provider = self.providers.get(channel)
        if not provider:
            raise ValueError(f"Unsupported channel: {channel}")
        return provider.send(recipient=recipient, subject=subject, body=body, html_body=html_body)


def is_queued_provider_result(channel: str, provider_result: str | None) -> bool:
    value = str(provider_result or "").strip()
    return channel == "whatsapp" and value.startswith("queued_whatsapp:")


def process_whatsapp_webhook_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Process Meta WhatsApp webhook payload (delivery statuses + incoming replies)."""
    if not isinstance(payload, Mapping):
        return {"status_updates": 0, "replies": 0}

    if "entry" not in payload:
        # Backward compatibility with the previous flat payload format.
        return _process_legacy_flat_payload(payload)

    from customer_applications.models import WorkflowNotification

    handled = {"status_updates": 0, "replies": 0}
    entries = payload.get("entry") or []

    for entry in entries:
        changes = (entry or {}).get("changes") or []
        for change in changes:
            value = (change or {}).get("value") or {}

            for status_data in value.get("statuses") or []:
                message_id = str(status_data.get("id") or "")
                message_status = str(status_data.get("status") or "").lower()
                recipient_id = str(status_data.get("recipient_id") or "")

                notification = None
                if message_id:
                    notification = (
                        WorkflowNotification.objects.filter(external_reference=message_id).order_by("-id").first()
                    )
                if notification is None and recipient_id:
                    notification = (
                        WorkflowNotification.objects.filter(recipient__in=_whatsapp_recipient_variants(recipient_id))
                        .exclude(status=WorkflowNotification.STATUS_FAILED)
                        .order_by("-id")
                        .first()
                    )
                if not notification:
                    continue

                note = f"Meta status: {message_status or 'unknown'}"
                status_errors = status_data.get("errors") or []
                if status_errors:
                    error = status_errors[0] or {}
                    error_fragments = []
                    if error.get("code"):
                        error_fragments.append(f"code={error.get('code')}")
                    if error.get("title"):
                        error_fragments.append(f"title={error.get('title')}")
                    if error.get("details"):
                        error_fragments.append(f"details={error.get('details')}")
                    if error_fragments:
                        note = f"{note} ({', '.join(error_fragments)})"

                notification.provider_message = _append_provider_message(notification.provider_message, note)
                _apply_whatsapp_status_update(notification, message_status=message_status)
                handled["status_updates"] += 1

            for message_data in value.get("messages") or []:
                from_number = str(message_data.get("from") or "")
                message_id = str(message_data.get("id") or "")
                context_message_id = str(((message_data.get("context") or {}).get("id")) or "")
                incoming_body = _extract_incoming_message_body(message_data)
                if not from_number:
                    continue

                target_notification = None
                if context_message_id:
                    target_notification = (
                        WorkflowNotification.objects.filter(external_reference=context_message_id)
                        .order_by("-id")
                        .first()
                    )
                if target_notification is None:
                    target_notification = (
                        WorkflowNotification.objects.filter(recipient__in=_whatsapp_recipient_variants(from_number))
                        .exclude(status=WorkflowNotification.STATUS_FAILED)
                        .order_by("-id")
                        .first()
                    )
                if not target_notification:
                    continue

                timestamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
                note = (
                    f"Customer reply ({timestamp}) from {from_number}"
                    f"{f' message_id={message_id}' if message_id else ''}: {incoming_body}"
                )
                target_notification.provider_message = _append_provider_message(
                    target_notification.provider_message,
                    note,
                )
                target_notification.save(update_fields=["provider_message", "updated_at"])
                handled["replies"] += 1

    logger.info(
        "Processed WhatsApp webhook payload: status_updates=%s replies=%s",
        handled["status_updates"],
        handled["replies"],
    )
    return handled


def _process_legacy_flat_payload(payload: Mapping[str, Any]) -> dict[str, Any]:
    """Support the previous flat payload format for backward compatibility."""
    from customer_applications.models import WorkflowNotification

    data = {k: _first_value(v) for k, v in dict(payload).items()}
    message_sid = data.get("MessageSid", "")
    message_status = data.get("MessageStatus", "")
    from_number = data.get("From", "")
    incoming_body = data.get("Body", "")
    replied_message_sid = data.get("OriginalRepliedMessageSid", "")

    handled = {"status_updates": 0, "replies": 0}

    if message_sid and message_status:
        notification = WorkflowNotification.objects.filter(external_reference=message_sid).order_by("-id").first()
        if notification:
            note = f"Legacy status: {message_status}"
            error_code = data.get("ErrorCode")
            error_message = data.get("ErrorMessage")
            if error_code or error_message:
                note = f"{note} (error_code={error_code}, error_message={error_message})"

            notification.provider_message = _append_provider_message(notification.provider_message, note)
            normalized_status = "failed" if message_status == "undelivered" else message_status
            _apply_whatsapp_status_update(notification, message_status=normalized_status)
            handled["status_updates"] += 1

    if incoming_body and from_number:
        target_notification = None
        if replied_message_sid:
            target_notification = (
                WorkflowNotification.objects.filter(external_reference=replied_message_sid).order_by("-id").first()
            )
        if target_notification is None:
            target_notification = (
                WorkflowNotification.objects.filter(recipient__in=_whatsapp_recipient_variants(from_number))
                .exclude(status=WorkflowNotification.STATUS_FAILED)
                .order_by("-id")
                .first()
            )

        if target_notification:
            timestamp = timezone.localtime(timezone.now()).strftime("%Y-%m-%d %H:%M:%S")
            note = f"Customer reply ({timestamp}) from {from_number}: {incoming_body}"
            target_notification.provider_message = _append_provider_message(
                target_notification.provider_message,
                note,
            )
            target_notification.save(update_fields=["provider_message", "updated_at"])
            handled["replies"] += 1

    logger.info(
        "Processed legacy WhatsApp webhook payload: status_updates=%s replies=%s",
        handled["status_updates"],
        handled["replies"],
    )
    return handled


def verify_meta_webhook_signature(raw_body: bytes, signature_header: str | None) -> bool:
    """Validate X-Hub-Signature-256 for Meta webhooks."""
    app_secret = getattr(settings, "META_APP_SECRET", "")
    if not app_secret:
        return True
    if not signature_header:
        return False

    expected = hmac.new(app_secret.encode("utf-8"), raw_body, hashlib.sha256).hexdigest()
    expected_header = f"sha256={expected}"
    return hmac.compare_digest(expected_header, signature_header.strip())


def _append_provider_message(existing: str, new_line: str) -> str:
    if existing:
        return f"{existing}\n{new_line}"
    return new_line


def _first_value(value: Any) -> str:
    if isinstance(value, (list, tuple)):
        return str(value[0]) if value else ""
    if value is None:
        return ""
    if isinstance(value, datetime):
        return timezone.localtime(value).isoformat()
    return str(value)


def _whatsapp_recipient_variants(value: str) -> list[str]:
    raw = (value or "").strip()
    if not raw:
        return []

    without_prefix = raw[len("whatsapp:") :] if raw.startswith("whatsapp:") else raw
    digits = re.sub(r"[^\d]", "", without_prefix)
    plus_number = f"+{digits}" if digits else ""
    clean_with_plus_or_plain = re.sub(r"[^\d+]", "", without_prefix)

    variants = {raw, without_prefix}
    if digits:
        variants.add(digits)
    if plus_number:
        variants.add(plus_number)
        variants.add(f"whatsapp:{plus_number}")
    if clean_with_plus_or_plain:
        variants.add(clean_with_plus_or_plain)

    return [item for item in variants if item]


def _extract_incoming_message_body(message_data: Mapping[str, Any]) -> str:
    message_type = str(message_data.get("type") or "").lower()
    if message_type == "text":
        return str((message_data.get("text") or {}).get("body") or "").strip()
    if message_type == "button":
        return str((message_data.get("button") or {}).get("text") or "").strip()
    if message_type == "interactive":
        interactive = message_data.get("interactive") or {}
        button_reply = interactive.get("button_reply") or {}
        list_reply = interactive.get("list_reply") or {}
        return str(button_reply.get("title") or list_reply.get("title") or "").strip()
    return f"[{message_type or 'unknown'} message]"


def _extract_meta_error_code(response: requests.Response) -> int | None:
    info = _extract_meta_error_info(response)
    return info.get("code")


def _extract_meta_error_info(response: requests.Response) -> dict[str, int | None]:
    try:
        data = response.json() or {}
    except Exception:
        return {"code": None, "error_subcode": None}

    error = data.get("error") or {}
    code = _safe_int(error.get("code"))
    subcode = _safe_int(error.get("error_subcode"))
    return {"code": code, "error_subcode": subcode}


def _response_has_expired_token_error(response: requests.Response) -> bool:
    if response.status_code not in {400, 401, 403}:
        return False

    error_info = _extract_meta_error_info(response)
    if error_info.get("code") == 190:
        return True

    try:
        payload = response.json() or {}
    except Exception:
        return False
    error_type = str((payload.get("error") or {}).get("type") or "").strip().lower()
    return error_type == "oauthexception"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None


def _apply_whatsapp_status_update(notification, *, message_status: str) -> None:
    from customer_applications.models import WorkflowNotification

    update_fields = ["provider_message", "updated_at"]
    next_status = _resolve_whatsapp_next_status(current_status=notification.status, meta_status=message_status)
    if next_status and next_status != notification.status:
        notification.status = next_status
        update_fields.append("status")

    if next_status in {
        WorkflowNotification.STATUS_SENT,
        WorkflowNotification.STATUS_DELIVERED,
        WorkflowNotification.STATUS_READ,
    } and not notification.sent_at:
        notification.sent_at = timezone.now()
        update_fields.append("sent_at")

    notification.save(update_fields=update_fields)


def _resolve_whatsapp_next_status(*, current_status: str, meta_status: str) -> str | None:
    from customer_applications.models import WorkflowNotification

    normalized_meta_status = _normalize_meta_status(meta_status)
    if not normalized_meta_status:
        return None

    mapped = {
        WHATSAPP_META_STATUS_SENT: WorkflowNotification.STATUS_SENT,
        WHATSAPP_META_STATUS_DELIVERED: WorkflowNotification.STATUS_DELIVERED,
        WHATSAPP_META_STATUS_READ: WorkflowNotification.STATUS_READ,
        WHATSAPP_META_STATUS_FAILED: WorkflowNotification.STATUS_FAILED,
    }[normalized_meta_status]

    if current_status in {WorkflowNotification.STATUS_CANCELLED, WorkflowNotification.STATUS_FAILED}:
        return current_status

    if mapped == WorkflowNotification.STATUS_FAILED:
        if current_status in {WorkflowNotification.STATUS_DELIVERED, WorkflowNotification.STATUS_READ}:
            return current_status
        return mapped

    current_rank = _WHATSAPP_PROGRESS_RANK.get(str(current_status or "").strip().lower())
    mapped_rank = _WHATSAPP_PROGRESS_RANK.get(mapped)
    if current_rank is not None and mapped_rank is not None and current_rank > mapped_rank:
        return current_status
    return mapped


def _normalize_meta_status(value: Any) -> str:
    normalized = str(value or "").strip().lower()
    if normalized in {
        WHATSAPP_META_STATUS_SENT,
        WHATSAPP_META_STATUS_DELIVERED,
        WHATSAPP_META_STATUS_READ,
        WHATSAPP_META_STATUS_FAILED,
    }:
        return normalized
    return ""


def _extract_meta_status_from_response(data: Mapping[str, Any]) -> str:
    raw_status = data.get("message_status") or data.get("status")
    if raw_status:
        return _normalize_meta_status(raw_status)

    statuses = data.get("statuses") or []
    if isinstance(statuses, list) and statuses:
        first_status = statuses[0] or {}
        if isinstance(first_status, Mapping):
            return _normalize_meta_status(first_status.get("status"))
    return ""
