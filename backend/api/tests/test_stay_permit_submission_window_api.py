import json
from datetime import date

from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.test import TestCase, override_settings
from django.urls import reverse
from products.models import DocumentType, Product

TEST_CACHES = {
    "default": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "stay-permit-window-default-cache",
    },
    "select2": {
        "BACKEND": "django.core.cache.backends.locmem.LocMemCache",
        "LOCATION": "stay-permit-window-select2-cache",
    },
}


@override_settings(CACHES=TEST_CACHES)
class StayPermitSubmissionWindowApiTests(TestCase):
    def setUp(self):
        user_model = get_user_model()
        self.user = user_model.objects.create_superuser(
            username="staypermit-admin",
            email="staypermit@example.com",
            password="password",
        )
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            customer_type="person",
            first_name="Stay",
            last_name="Permit",
            active=True,
        )

        self.stay_doc_type = DocumentType.objects.create(
            name="ITAS",
            is_stay_permit=True,
            has_expiration_date=False,
            has_file=True,
        )
        self.non_stay_doc_type = DocumentType.objects.create(
            name="Passport",
            has_expiration_date=True,
            has_file=True,
        )

        self.product = Product.objects.create(
            name="Stay Permit Visa",
            code="SPV-1",
            product_type="visa",
            required_documents="ITAS",
            optional_documents="Passport",
            application_window_days=30,
        )

    def _extract_doc_date_errors(self, payload: dict) -> list[str]:
        errors = payload.get("errors", {}) if isinstance(payload, dict) else {}
        if not isinstance(errors, dict):
            return []
        raw = errors.get("docDate") or errors.get("doc_date") or []
        if isinstance(raw, list):
            return [str(item) for item in raw]
        return [str(raw)]

    def _create_application_with_stay_permit_doc(self, expiration: date) -> DocApplication:
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 3, 15),
            created_by=self.user,
        )
        Document.objects.create(
            doc_application=application,
            doc_type=self.stay_doc_type,
            expiration_date=expiration,
            required=True,
            created_by=self.user,
        )
        return application

    def test_document_type_stay_permit_forces_has_expiration_date(self):
        self.assertTrue(self.stay_doc_type.has_expiration_date)

    def test_document_type_without_expiration_clears_expiring_threshold_days(self):
        doc_type = DocumentType.objects.create(
            name="Threshold Cleared",
            has_expiration_date=True,
            expiring_threshold_days=20,
            has_file=True,
        )
        doc_type.has_expiration_date = False
        doc_type.save()
        doc_type.refresh_from_db()
        self.assertIsNone(doc_type.expiring_threshold_days)

    def test_document_type_api_create_and_update_roundtrip_expiring_threshold_days(self):
        create_payload = {
            "name": "Threshold API",
            "description": "test",
            "aiValidation": True,
            "hasExpirationDate": True,
            "expiringThresholdDays": 15,
            "hasFile": True,
            "hasDocNumber": False,
            "hasDetails": False,
            "isInRequiredDocuments": False,
            "deprecated": False,
            "isStayPermit": False,
        }
        create_response = self.client.post(
            reverse("document-types-list"),
            data=json.dumps(create_payload),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        doc_type_id = create_response.json()["id"]
        created = DocumentType.objects.get(pk=doc_type_id)
        self.assertEqual(created.expiring_threshold_days, 15)

        update_payload = {
            **create_payload,
            "expiringThresholdDays": 7,
        }
        update_response = self.client.put(
            reverse("document-types-detail", kwargs={"pk": doc_type_id}),
            data=json.dumps(update_payload),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)
        created.refresh_from_db()
        self.assertEqual(created.expiring_threshold_days, 7)

    def test_rejects_doc_date_before_first_submission_day(self):
        application = self._create_application_with_stay_permit_doc(date(2026, 3, 31))
        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.id}),
            data=json.dumps({"doc_date": "2026-02-28"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        errors = self._extract_doc_date_errors(response.json())
        self.assertTrue(any("2026-03-01" in message for message in errors))

    def test_rejects_doc_date_after_last_submission_day(self):
        application = self._create_application_with_stay_permit_doc(date(2026, 3, 31))
        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.id}),
            data=json.dumps({"doc_date": "2026-04-01", "due_date": "2026-04-01"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        errors = self._extract_doc_date_errors(response.json())
        self.assertTrue(any("Application date must be between" in message for message in errors))

    def test_accepts_doc_date_within_submission_window(self):
        application = self._create_application_with_stay_permit_doc(date(2026, 3, 31))
        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.id}),
            data=json.dumps({"doc_date": "2026-03-10"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.doc_date, date(2026, 3, 10))

    def test_partial_update_without_doc_date_or_product_does_not_revalidate_window(self):
        application = self._create_application_with_stay_permit_doc(date(2026, 3, 31))
        self.product.application_window_days = 10
        self.product.save(update_fields=["application_window_days"])

        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.id}),
            data=json.dumps({"notes": "Updated notes only"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.notes, "Updated notes only")

    def test_uses_earliest_expiration_when_multiple_stay_permits_exist(self):
        second_stay_doc_type = DocumentType.objects.create(
            name="KITAS",
            is_stay_permit=True,
            has_expiration_date=True,
            has_file=True,
        )
        self.product.required_documents = "ITAS,KITAS"
        self.product.application_window_days = 10
        self.product.save(update_fields=["required_documents", "application_window_days"])

        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 3, 25),
            created_by=self.user,
        )
        Document.objects.create(
            doc_application=application,
            doc_type=self.stay_doc_type,
            expiration_date=date(2026, 4, 1),
            required=True,
            created_by=self.user,
        )
        Document.objects.create(
            doc_application=application,
            doc_type=second_stay_doc_type,
            expiration_date=date(2026, 5, 1),
            required=True,
            created_by=self.user,
        )

        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.id}),
            data=json.dumps({"doc_date": "2026-03-20"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        errors = self._extract_doc_date_errors(response.json())
        self.assertTrue(any("2026-03-22" in message for message in errors))

    def test_allows_updates_when_no_qualifying_stay_permit_expiration_exists(self):
        application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=date(2026, 1, 5),
            created_by=self.user,
        )
        Document.objects.create(
            doc_application=application,
            doc_type=self.stay_doc_type,
            expiration_date=None,
            required=True,
            created_by=self.user,
        )

        response = self.client.patch(
            reverse("customer-applications-detail", kwargs={"pk": application.id}),
            data=json.dumps({"doc_date": "2026-01-01"}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)
        application.refresh_from_db()
        self.assertEqual(application.doc_date, date(2026, 1, 1))

    def test_create_application_allows_when_no_stay_permit_expiration_exists_yet(self):
        payload = {
            "customer": self.customer.id,
            "product": self.product.id,
            "doc_date": "2026-01-15",
            "due_date": "2026-01-15",
            "document_types": [{"doc_type_id": self.stay_doc_type.id, "required": True}],
        }
        response = self.client.post(
            reverse("customer-applications-list"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 201)

    def test_product_create_and_update_persists_application_window_days(self):
        create_payload = {
            "name": "Windowed Product",
            "code": "WND-1",
            "productType": "visa",
            "requiredDocumentIds": [self.stay_doc_type.id],
            "optionalDocumentIds": [],
            "applicationWindowDays": 45,
        }
        create_response = self.client.post(
            reverse("products-list"),
            data=json.dumps(create_payload),
            content_type="application/json",
        )
        self.assertEqual(create_response.status_code, 201)
        product_id = create_response.json()["id"]

        created = Product.objects.get(pk=product_id)
        self.assertEqual(created.application_window_days, 45)

        update_payload = {
            "name": "Windowed Product",
            "code": "WND-1",
            "productType": "visa",
            "requiredDocumentIds": [self.stay_doc_type.id],
            "optionalDocumentIds": [],
            "applicationWindowDays": 60,
        }
        update_response = self.client.put(
            reverse("products-detail", kwargs={"pk": product_id}),
            data=json.dumps(update_payload),
            content_type="application/json",
        )
        self.assertEqual(update_response.status_code, 200)

        created.refresh_from_db()
        self.assertEqual(created.application_window_days, 60)
