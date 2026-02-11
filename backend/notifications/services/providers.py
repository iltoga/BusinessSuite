from abc import ABC, abstractmethod

from django.conf import settings
from django.core.mail import send_mail


class NotificationProvider(ABC):
    channel: str

    @abstractmethod
    def send(self, recipient: str, subject: str, body: str) -> str:
        raise NotImplementedError


class EmailNotificationProvider(NotificationProvider):
    channel = "email"

    def send(self, recipient: str, subject: str, body: str) -> str:
        sender = getattr(settings, "NOTIFICATION_FROM_EMAIL", "dewi@revisbali.com")
        count = send_mail(subject, body, sender, [recipient], fail_silently=False)
        return f"sent:{count}"


class NotificationDispatcher:
    def __init__(self):
        self.providers = {"email": EmailNotificationProvider()}

    def send(self, channel: str, recipient: str, subject: str, body: str) -> str:
        provider = self.providers.get(channel)
        if not provider:
            raise ValueError(f"Unsupported channel: {channel}")
        return provider.send(recipient=recipient, subject=subject, body=body)
