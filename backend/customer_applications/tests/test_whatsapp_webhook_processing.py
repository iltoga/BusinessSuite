from django.contrib.auth import get_user_model
from django.test import TestCase

from customer_applications.models import DocApplication, WorkflowNotification
from customers.models import Customer
from notifications.services.providers import process_whatsapp_webhook_payload
from products.models import Product

User = get_user_model()


class WhatsappWebhookProcessingTests(TestCase):
    def setUp(self):
        self.user = User.objects.create_user("webhook-user", "webhook@example.com", "pass")
        self.customer = Customer.objects.create(
            first_name="Webhook",
            last_name="Customer",
            whatsapp="+628123456789",
        )
        self.product = Product.objects.create(name="Webhook Product", code="WB-01", required_documents="Passport")
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date="2026-02-12",
            due_date="2026-02-13",
            created_by=self.user,
        )
        self.notification = WorkflowNotification.objects.create(
            channel=DocApplication.NOTIFY_CHANNEL_WHATSAPP,
            subject="Reminder",
            body="Body",
            recipient=self.customer.whatsapp,
            doc_application=self.application,
            status=WorkflowNotification.STATUS_SENT,
            external_reference="wamid.HBgLMjQ0NTU2Njc3ODg5FQIAERgSNzY3QjM1MTQ4M0I2RDA3AA==",
        )

    def test_status_callback_updates_notification(self):
        result = process_whatsapp_webhook_payload(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "123456",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "statuses": [
                                        {
                                            "id": self.notification.external_reference,
                                            "status": "read",
                                            "recipient_id": "628123456789",
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(result["status_updates"], 1)
        self.notification.refresh_from_db()
        self.assertEqual(self.notification.status, WorkflowNotification.STATUS_READ)
        self.assertIn("Meta status: read", self.notification.provider_message)

    def test_incoming_reply_is_attached_to_original_notification(self):
        result = process_whatsapp_webhook_payload(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "123456",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "messages": [
                                        {
                                            "from": "628123456789",
                                            "id": "wamid.HBgLMjQ0NTU2Njc3ODg5FQIAEhggRjA4QjY3RjU2N0YxRjU4RDk1QkQ5N0M2QkQ5QzQ0RjUA",
                                            "timestamp": "1700000000",
                                            "type": "text",
                                            "text": {"body": "Ok, thank you"},
                                            "context": {"id": self.notification.external_reference},
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(result["replies"], 1)
        self.notification.refresh_from_db()
        self.assertIn("Ok, thank you", self.notification.provider_message)

    def test_incoming_reply_matches_recipient_without_context_id(self):
        self.notification.external_reference = ""
        self.notification.save(update_fields=["external_reference", "updated_at"])

        result = process_whatsapp_webhook_payload(
            {
                "object": "whatsapp_business_account",
                "entry": [
                    {
                        "id": "123456",
                        "changes": [
                            {
                                "field": "messages",
                                "value": {
                                    "messages": [
                                        {
                                            "from": "628123456789",
                                            "id": "wamid.HBgLMjQ0NTU2Njc3ODg5FQIAEhggMzcxNDhGODQ2RkY2MEE5Q0E4M0Q5NjIwNzQ3NzQ5NzEA",
                                            "timestamp": "1700000001",
                                            "type": "text",
                                            "text": {"body": "Can we move this deadline?"},
                                        }
                                    ]
                                },
                            }
                        ],
                    }
                ],
            }
        )

        self.assertEqual(result["replies"], 1)
        self.notification.refresh_from_db()
        self.assertIn("Can we move this deadline?", self.notification.provider_message)
