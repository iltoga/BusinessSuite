from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.utils import timezone

from notifications.services.providers import NotificationDispatcher


class Command(BaseCommand):
    help = "Send a WhatsApp message through the configured provider (Meta Cloud API)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--to",
            dest="to",
            default="",
            help="Destination WhatsApp number (E.164 preferred). Defaults to settings.WHATSAPP_TEST_NUMBER.",
        )
        parser.add_argument(
            "--message",
            dest="message",
            default="",
            help="Message body. Defaults to a short timestamped test message.",
        )
        parser.add_argument(
            "--subject",
            dest="subject",
            default="",
            help="Optional subject for internal logging only.",
        )

    def handle(self, *args, **options):
        to_number = (options.get("to") or "").strip() or getattr(settings, "WHATSAPP_TEST_NUMBER", "")
        if not to_number:
            raise CommandError("No destination number provided. Set --to or WHATSAPP_TEST_NUMBER in settings.")

        message = (options.get("message") or "").strip()
        if not message:
            now = timezone.localtime().strftime("%Y-%m-%d %H:%M:%S")
            message = f"RevisBali CRM WhatsApp test message ({now})."

        subject = (options.get("subject") or "").strip() or "Django WhatsApp command"

        dispatcher = NotificationDispatcher()
        try:
            message_id = dispatcher.send(
                channel="whatsapp",
                recipient=to_number,
                subject=subject,
                body=message,
            )
        except Exception as exc:
            raise CommandError(f"WhatsApp send failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("WhatsApp message sent successfully."))
        self.stdout.write(f"To: {to_number}")
        self.stdout.write(f"Message ID: {message_id}")
