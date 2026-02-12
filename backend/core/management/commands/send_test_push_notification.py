import json

from django.contrib.auth import get_user_model
from django.core.management.base import BaseCommand, CommandError

from core.services.push_notifications import FcmConfigurationError, PushNotificationService

User = get_user_model()


class Command(BaseCommand):
    help = "Send a real browser push notification to a registered user's devices via FCM HTTP v1."

    def add_arguments(self, parser):
        parser.add_argument("--user-id", dest="user_id", type=int, required=True, help="Target user id.")
        parser.add_argument(
            "--title",
            dest="title",
            default="Revis Bali CRM Push Test",
            help="Notification title.",
        )
        parser.add_argument(
            "--body",
            dest="body",
            default="Push notification test from Django management command.",
            help="Notification body.",
        )
        parser.add_argument(
            "--link",
            dest="link",
            default="/",
            help="Optional app link opened when clicking the notification.",
        )
        parser.add_argument(
            "--data",
            dest="data",
            default="{}",
            help='Optional JSON object added as FCM data payload (example: \'{"type":"test"}\').',
        )

    def handle(self, *args, **options):
        user_id = options["user_id"]
        title = str(options["title"]).strip()
        body = str(options["body"]).strip()
        link = str(options.get("link") or "").strip() or None
        raw_data = str(options.get("data") or "{}").strip()

        try:
            data_payload = json.loads(raw_data)
        except json.JSONDecodeError as exc:
            raise CommandError(f"Invalid --data JSON: {exc}") from exc
        if not isinstance(data_payload, dict):
            raise CommandError("--data must be a JSON object")

        user = User.objects.filter(pk=user_id).first()
        if not user:
            raise CommandError(f"User with id {user_id} not found")

        try:
            result = PushNotificationService().send_to_user(
                user=user,
                title=title,
                body=body,
                data=data_payload,
                link=link,
            )
        except FcmConfigurationError as exc:
            raise CommandError(f"FCM configuration error: {exc}") from exc
        except Exception as exc:
            raise CommandError(f"Push notification failed: {exc}") from exc

        self.stdout.write(self.style.SUCCESS("Push notification send attempted."))
        self.stdout.write(f"User ID: {user.id}")
        self.stdout.write(f"Sent: {result.sent}")
        self.stdout.write(f"Failed: {result.failed}")
        self.stdout.write(f"Skipped: {result.skipped}")
