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

logger = logging.getLogger(__name__)


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
    - META_GRAPH_API_VERSION (default: v22.0)
    """

    channel = "whatsapp"

    def send(self, recipient: str, subject: str, body: str, html_body: str | None = None) -> str:
        access_token = getattr(settings, "META_WHATSAPP_ACCESS_TOKEN", "")
        phone_number_id = getattr(settings, "META_PHONE_NUMBER_ID", "") or getattr(
            settings, "META_WHATSAPP_BUSINESS_NUMBER_ID", ""
        )
        graph_version = getattr(settings, "META_GRAPH_API_VERSION", "v22.0")

        if not access_token or not phone_number_id:
            logger.info("Meta WhatsApp credentials are not configured. Returning queued placeholder.")
            return f"queued_whatsapp:{recipient}"

        url = f"https://graph.facebook.com/{graph_version}/{phone_number_id}/messages"
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Content-Type": "application/json",
        }
        payload = {
            "messaging_product": "whatsapp",
            "to": self._normalize_meta_phone_number(recipient),
            "type": "text",
            "text": {
                "preview_url": False,
                "body": body,
            },
        }

        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code >= 400:
            code = _extract_meta_error_code(response)
            # Free-form text can be blocked outside the customer service window.
            # Retry with an approved template in this case (common with test/sandbox setups).
            if code in {131047, 470}:
                return self._send_template_message(
                    url=url,
                    headers=headers,
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

    def _send_template_message(self, *, url: str, headers: Mapping[str, str], recipient: str) -> str:
        template_name = getattr(settings, "META_WHATSAPP_DEFAULT_TEMPLATE_NAME", "hello_world")
        language_code = getattr(settings, "META_WHATSAPP_DEFAULT_TEMPLATE_LANG", "en_US")
        payload = {
            "messaging_product": "whatsapp",
            "to": self._normalize_meta_phone_number(recipient),
            "type": "template",
            "template": {
                "name": template_name,
                "language": {"code": language_code},
            },
        }
        response = requests.post(url, json=payload, headers=headers, timeout=20)
        if response.status_code >= 400:
            raise RuntimeError(f"WhatsApp template send failed ({response.status_code}): {response.text}")

        data = response.json()
        messages = data.get("messages") or []
        message_id = messages[0].get("id") if messages else None
        if not message_id:
            raise RuntimeError("WhatsApp template send succeeded but no message id returned by Meta.")
        return str(message_id)


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
                update_fields = ["provider_message", "updated_at"]
                if message_status in {"failed"}:
                    notification.status = WorkflowNotification.STATUS_FAILED
                    update_fields.append("status")
                elif message_status in {"sent", "delivered", "read"}:
                    notification.status = WorkflowNotification.STATUS_SENT
                    update_fields.append("status")
                    if not notification.sent_at:
                        notification.sent_at = timezone.now()
                        update_fields.append("sent_at")

                notification.save(update_fields=update_fields)
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
            if message_status in {"failed", "undelivered"}:
                notification.status = WorkflowNotification.STATUS_FAILED
            elif message_status in {"sent", "delivered", "read"}:
                notification.status = WorkflowNotification.STATUS_SENT
                if not notification.sent_at:
                    notification.sent_at = timezone.now()

            notification.save(update_fields=["status", "provider_message", "sent_at", "updated_at"])
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
    try:
        data = response.json() or {}
    except Exception:
        return None
    error = data.get("error") or {}
    code = error.get("code")
    try:
        return int(code) if code is not None else None
    except (TypeError, ValueError):
        return None
