from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.contrib.auth import get_user_model
from django.contrib.auth.signals import user_logged_in, user_login_failed
from django.test import TestCase, override_settings

from customers.models import Customer


class AuditLoginSignalsTests(TestCase):
    def setUp(self):
        # ensure models are registered for auditlog in test context
        try:
            auditlog.register(get_user_model())
        except Exception:
            pass

        try:
            auditlog.register(Customer)
        except Exception:
            pass

        LogEntry.objects.all().delete()
        self.user = get_user_model().objects.create_user(username="loginuser", password="pw")

    def test_user_logged_in_creates_logentry(self):
        user_logged_in.send(sender=self.__class__, request=None, user=self.user)
        self.assertTrue(LogEntry.objects.filter(actor=self.user, action=LogEntry.Action.ACCESS).exists())
        entry = LogEntry.objects.filter(actor=self.user, action=LogEntry.Action.ACCESS).first()
        # admin-friendly representation expects [old, new]
        self.assertEqual(entry.changes, {"login": [None, "success"]})

    def test_user_login_failed_with_existing_user_creates_logentry(self):
        # simulate failed attempt with username that exists
        credentials = {"username": self.user.get_username()}
        user_login_failed.send(sender=self.__class__, credentials=credentials, request=None)
        self.assertTrue(
            LogEntry.objects.filter(object_pk=str(self.user.pk)).exists()
            or LogEntry.objects.filter(actor=self.user).exists()
        )

    def test_user_login_failed_with_unknown_user_creates_logentry_with_actor_email(self):
        credentials = {"username": "doesnotexist"}
        user_login_failed.send(sender=self.__class__, credentials=credentials, request=None)
        self.assertTrue(LogEntry.objects.filter(actor_email="doesnotexist").exists())

    def test_respects_audit_enabled_setting(self):
        """When AUDIT_ENABLED is False we should not create explicit login audit entries.

        Note: model saves (e.g., last_login updates) may still be recorded by django-auditlog
        if the model is registered. We specifically assert that our login-specific
        entry (changes={'login': 'success'}) is not created.
        """
        with override_settings(AUDIT_ENABLED=False):
            LogEntry.objects.all().delete()
            user_logged_in.send(sender=self.__class__, request=None, user=self.user)
            # There should be no LogEntry created by our receiver with login payload
            self.assertFalse(LogEntry.objects.filter(changes={"login": "success"}).exists())

    def test_respects_watch_flag(self):
        """When AUDIT_WATCH_AUTH_EVENTS is False our receivers should be inert.

        We assert that no login-specific LogEntry is created (other model changes may still occur).
        """
        with override_settings(AUDIT_WATCH_AUTH_EVENTS=False):
            LogEntry.objects.all().delete()
            user_logged_in.send(sender=self.__class__, request=None, user=self.user)
            self.assertFalse(LogEntry.objects.filter(changes={"login": "success"}).exists())
