from auditlog.models import LogEntry
from auditlog.registry import auditlog
from django.contrib.auth import authenticate, get_user_model
from django.contrib.auth.signals import user_login_failed
from django.test import Client, RequestFactory, TestCase

from customers.models import Customer


class AuditlogEventsTests(TestCase):
    def setUp(self):
        # Ensure models we exercise are registered with auditlog
        auditlog.register(Customer)
        self.client = Client()
        self.factory = RequestFactory()
        User = get_user_model()
        self.user = User.objects.create_user(username="tester", password="pass")

    def test_crud_create_update_delete_audited_and_read_not_audited(self):
        # initial count
        initial = LogEntry.objects.count()

        # Create
        c = Customer.objects.create(first_name="Alice", last_name="Smith", email="alice@example.com")
        # There should be a CREATE log entry for this object
        self.assertTrue(
            LogEntry.objects.filter(object_pk=str(c.pk), action=LogEntry.Action.CREATE).exists(),
            "Expected a CREATE LogEntry for new Customer",
        )

        # Update
        LogEntry.objects.all().delete()
        c.first_name = "Alice X"
        c.save()
        self.assertTrue(
            LogEntry.objects.filter(object_pk=str(c.pk), action=LogEntry.Action.UPDATE).exists(),
            "Expected an UPDATE LogEntry when Customer is saved",
        )

        # Read - should NOT create an access log entry by default
        before = LogEntry.objects.count()
        _ = Customer.objects.get(pk=c.pk)
        after = LogEntry.objects.count()
        self.assertEqual(before, after, "Reading an object should not create an audit LogEntry by default")

        # Delete
        LogEntry.objects.all().delete()
        c_pk = c.pk
        c.delete()
        self.assertTrue(
            LogEntry.objects.filter(object_pk=str(c_pk), action=LogEntry.Action.DELETE).exists(),
            "Expected a DELETE LogEntry when Customer is deleted",
        )

    def test_successful_login_is_audited(self):
        # login via client -> should trigger user_logged_in signal and our receiver
        logged_in = self.client.login(username="tester", password="pass")
        self.assertTrue(logged_in, "Client login should succeed for valid credentials")

        # There should be a LogEntry for this user with action ACCESS
        self.assertTrue(
            LogEntry.objects.filter(object_pk=str(self.user.pk), action=LogEntry.Action.ACCESS).exists(),
            "Expected an ACCESS LogEntry for successful login",
        )
        entry = LogEntry.objects.filter(object_pk=str(self.user.pk), action=LogEntry.Action.ACCESS).first()
        self.assertIsNotNone(entry)
        self.assertEqual(entry.changes, {"login": "success"})
        # actor should be the user (we set actor when creating via log_create)
        self.assertEqual(entry.actor_id, self.user.pk)

    def test_failed_login_is_audited_and_records_actor_email_when_user_missing(self):
        # Send a failed login signal for a non-existing username
        credentials = {"username": "ghost", "password": "x"}
        user_login_failed.send(sender=None, credentials=credentials, request=None)

        # Expect a LogEntry where object_pk == 'ghost' and actor_email == 'ghost'
        self.assertTrue(
            LogEntry.objects.filter(object_pk="ghost").exists(),
            "Expected an audit LogEntry for failed login attempt",
        )
        entry = LogEntry.objects.filter(object_pk="ghost").first()
        self.assertEqual(entry.changes, {"login": "failed"})
        self.assertEqual(entry.actor_email, "ghost")

    def test_failed_login_for_existing_user_is_attributed_to_user(self):
        # Send a failed login for an existing username
        credentials = {"username": self.user.get_username(), "password": "wrong"}
        user_login_failed.send(sender=None, credentials=credentials, request=None)

        # Expect an ACCESS LogEntry for that user with login failed
        self.assertTrue(
            LogEntry.objects.filter(object_pk=str(self.user.pk)).exists(),
            "Expected an ACCESS LogEntry for failed login for existing user",
        )
        entry = LogEntry.objects.filter(object_pk=str(self.user.pk)).first()
        self.assertEqual(entry.actor_id, self.user.pk)
        self.assertEqual(entry.changes, {"login": "failed"})
