import datetime
import json
import tempfile
from unittest.mock import patch

from core.models import Holiday
from customer_applications.models import DocApplication, Document
from customers.models import Customer
from django.contrib.auth import get_user_model
from django.core.files.storage import FileSystemStorage
from django.core.files.uploadedfile import SimpleUploadedFile
from django.db import connection
from django.test import TestCase
from django.test.utils import CaptureQueriesContext
from django.urls import reverse
from django.utils import timezone
from invoices.models import Invoice, InvoiceApplication
from PIL import Image
from products.models import Product
from products.models.document_type import DocumentType


class CustomerQuickCreateAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_customer_quick_create_accepts_passport_fields(self):
        url = reverse("api-customer-quick-create")
        data = {
            "title": "Mr",
            "customer_type": "person",
            "first_name": "John",
            "last_name": "Doe",
            "birthdate": "1990-01-01",
            "email": "john@example.com",
            "telephone": "081234567",
            "passport_number": "P12345678",
            "passport_issue_date": "2018-05-10",
            "passport_expiration_date": "2028-05-10",
        }
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 201)
        cust = Customer.objects.filter(first_name="John", last_name="Doe").first()
        self.assertIsNotNone(cust)
        self.assertEqual(cust.passport_number, "P12345678")
        self.assertEqual(str(cust.passport_issue_date), "2018-05-10")
        self.assertEqual(str(cust.passport_expiration_date), "2028-05-10")

    def test_customer_quick_create_rejects_duplicate_passport(self):
        # Existing customer with passport
        existing = Customer.objects.create(
            customer_type="person", first_name="A", last_name="User", passport_number="DUP123"
        )
        url = reverse("api-customer-quick-create")
        data = {"customer_type": "person", "first_name": "B", "last_name": "User", "passport_number": "DUP123"}
        response = self.client.post(url, data)
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        # Quick create returns errors under `errors`
        self.assertIn("errors", payload)
        errors = payload["errors"]
        self.assertIn("passportNumber", errors)
        messages = (
            errors["passportNumber"] if isinstance(errors["passportNumber"], list) else [errors["passportNumber"]]
        )
        self.assertIn("This passport number is already used by another customer.", messages)

    def test_customer_create_rejects_duplicate_passport_via_api(self):
        url = reverse("customers-list")
        data1 = {"customer_type": "person", "first_name": "X", "last_name": "One", "passport_number": "P-DUP-1"}
        response1 = self.client.post(url, data1)
        self.assertEqual(response1.status_code, 201)

        data2 = {"customer_type": "person", "first_name": "Y", "last_name": "Two", "passport_number": "P-DUP-1"}
        response2 = self.client.post(url, data2)
        self.assertEqual(response2.status_code, 400)
        payload = response2.json()
        # DRF returns field errors inside "errors" key because of custom exception handler
        self.assertIn("errors", payload)
        self.assertIn("passportNumber", payload["errors"])
        self.assertIn("customer with this passport number already exists.", payload["errors"]["passportNumber"])

    def test_customer_update_rejects_duplicate_passport(self):
        c1 = Customer.objects.create(customer_type="person", first_name="C", last_name="One", passport_number="P-1")
        c2 = Customer.objects.create(customer_type="person", first_name="D", last_name="Two", passport_number="P-2")
        url = reverse("customers-detail", args=[c2.id])
        response = self.client.patch(url, {"passport_number": "P-1"}, content_type="application/json")
        self.assertEqual(response.status_code, 400)
        payload = response.json()
        self.assertIn("errors", payload)
        self.assertIn("passportNumber", payload["errors"])
        self.assertIn("customer with this passport number already exists.", payload["errors"]["passportNumber"])

    @patch("customers.services.passport_file_processing.convert_and_resize_image")
    def test_customer_create_converts_pdf_passport_file_to_png(self, convert_mock):
        convert_mock.return_value = (Image.new("RGB", (1200, 800), color="white"), b"")

        upload = SimpleUploadedFile(
            "passport.pdf",
            b"%PDF-1.4 fake content",
            content_type="application/pdf",
        )
        with tempfile.TemporaryDirectory() as media_root:
            local_storage = FileSystemStorage(location=media_root, base_url="/media/")
            passport_field = Customer._meta.get_field("passport_file")
            with patch.object(passport_field, "storage", local_storage):
                response = self.client.post(
                    reverse("customers-list"),
                    {
                        "customer_type": "person",
                        "first_name": "Pdf",
                        "last_name": "Upload",
                        "passport_file": upload,
                    },
                )
                self.assertEqual(response.status_code, 201, response.content)

                created_id = response.json()["id"]
                customer = Customer.objects.get(pk=created_id)
                self.assertTrue(customer.passport_file.name.endswith(".png"))
                self.assertTrue(local_storage.exists(customer.passport_file.name))

                with customer.passport_file.open("rb") as stored_file:
                    self.assertEqual(stored_file.read(8), b"\x89PNG\r\n\x1a\n")

        convert_mock.assert_called_once()

    def test_customer_detail_returns_gender_display(self):
        from django.urls import reverse

        # Create a customer with a gender and fetch the detail view
        cust = Customer.objects.create(customer_type="person", first_name="Jane", last_name="Roe", gender="F")
        url = reverse("api-customer-detail", args=[cust.pk])
        # Default language
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Accept camelCase or snake_case
        self.assertTrue("gender_display" in data or "genderDisplay" in data)
        key = "gender_display" if "gender_display" in data else "genderDisplay"
        self.assertIsInstance(data[key], str)

        # Indonesian (document_lang) - if translations compiled, expect Indonesian translation
        url_id = f"{url}?document_lang=id"
        response_id = self.client.get(url_id)
        self.assertEqual(response_id.status_code, 200)
        data_id = response_id.json()
        self.assertTrue("gender_display" in data_id or "genderDisplay" in data_id)
        key_id = "gender_display" if "gender_display" in data_id else "genderDisplay"
        gender_display = data_id[key_id]
        self.assertIsInstance(gender_display, str)
        if gender_display != "Female":
            self.assertEqual(gender_display, "Perempuan")


class CustomerListAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="testadmin", email="admin@example.com", password="password")
        self.client.force_login(self.user)

    def test_customer_list_includes_passport_flags(self):
        today = timezone.now().date()
        expired = Customer.objects.create(
            customer_type="person",
            first_name="Expired",
            last_name="Customer",
            passport_expiration_date=today - datetime.timedelta(days=1),
        )
        expiring = Customer.objects.create(
            customer_type="person",
            first_name="Soon",
            last_name="Customer",
            passport_expiration_date=today + datetime.timedelta(days=30),
        )

        url = reverse("customers-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        expired_item = next(item for item in data["results"] if item["id"] == expired.id)
        expiring_item = next(item for item in data["results"] if item["id"] == expiring.id)

        self.assertTrue(expired_item["passportExpired"])
        self.assertFalse(expired_item["passportExpiringSoon"])
        self.assertTrue(expiring_item["passportExpiringSoon"])

    def test_toggle_active_endpoint(self):
        customer = Customer.objects.create(customer_type="person", first_name="Active", last_name="User")
        url = reverse("customers-toggle-active", args=[customer.id])
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        customer.refresh_from_db()
        self.assertFalse(customer.active)

    def test_uninvoiced_applications_endpoint(self):
        customer = Customer.objects.create(customer_type="person", first_name="Nina", last_name="Stone")
        product = Product.objects.create(name="KITAS", code="KITAS-1", product_type="visa")

        ready_app = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

        not_ready_app = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

        doc_type = DocumentType.objects.create(name="Passport Scan")
        Document.objects.create(
            doc_application=not_ready_app,
            doc_type=doc_type,
            required=True,
            created_by=self.user,
        )

        invoiced_app = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        invoice = Invoice.objects.create(
            customer=customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            created_by=self.user,
        )
        InvoiceApplication.objects.create(
            invoice=invoice,
            customer_application=invoiced_app,
            amount="100.00",
        )

        url = reverse("customers-uninvoiced-applications", args=[customer.id])
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()

        self.assertEqual(len(payload), 2)
        ids = {item["id"] for item in payload}
        self.assertSetEqual(ids, {ready_app.id, not_ready_app.id})

        ready_row = next(item for item in payload if item["id"] == ready_app.id)
        not_ready_row = next(item for item in payload if item["id"] == not_ready_app.id)

        ready_app.refresh_from_db()
        self.assertEqual(ready_row["statusDisplay"], ready_app.get_status_display())
        self.assertEqual(ready_row["productTypeDisplay"], "Visa")
        self.assertFalse(ready_row["hasInvoice"])
        self.assertIsNone(ready_row["invoiceId"])
        self.assertTrue(ready_row["isDocumentCollectionCompleted"])
        self.assertTrue(ready_row["readyForInvoice"])

        not_ready_app.refresh_from_db()
        self.assertFalse(not_ready_row["isDocumentCollectionCompleted"])
        expected_ready = not_ready_app.status in ("completed", "rejected")
        self.assertEqual(not_ready_row["readyForInvoice"], expected_ready)


class CustomerApplicationDetailAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="appadmin", email="app@example.com", password="password")
        self.client.force_login(self.user)

        self.customer = Customer.objects.create(
            customer_type="person",
            first_name="Ana",
            last_name="Doe",
            active=True,
            created_at=timezone.now(),
            updated_at=timezone.now(),
        )
        self.product = Product.objects.create(
            name="Visa Extension",
            code="VISA-EXT",
            product_type="visa",
            required_documents="Passport",
        )
        self.application = DocApplication.objects.create(
            customer=self.customer,
            product=self.product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )
        self.doc_type = DocumentType.objects.create(
            name="Passport",
            ai_validation=True,
            has_doc_number=True,
            has_expiration_date=True,
            has_file=True,
        )
        self.document = Document.objects.create(
            doc_application=self.application,
            doc_type=self.doc_type,
            created_by=self.user,
        )

    def test_application_detail_includes_documents(self):
        url = reverse("customer-applications-detail", kwargs={"pk": self.application.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(payload["id"], self.application.id)
        self.assertEqual(len(payload["documents"]), 1)
        self.assertEqual(payload["documents"][0]["docType"]["name"], "Passport")

    def test_application_detail_uses_cached_file_link_without_storage_url_lookup(self):
        Document.objects.filter(pk=self.document.pk).update(
            file="documents/customer_1/application_1/passport.pdf",
            file_link="https://example.test/documents/passport.pdf",
        )
        self.document.refresh_from_db()

        url = reverse("customer-applications-detail", kwargs={"pk": self.application.pk})
        with patch.object(
            self.document.file.storage,
            "url",
            side_effect=AssertionError("storage.url should not be called for cached detail responses"),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        self.assertEqual(
            payload["documents"][0]["file"],
            "https://example.test/documents/passport.pdf",
        )

    def test_application_detail_ktp_sponsor_actions_skip_remote_exists_probe(self):
        ktp_doc_type = DocumentType.objects.create(name="KTP Sponsor", has_file=True)
        Document.objects.create(
            doc_application=self.application,
            doc_type=ktp_doc_type,
            created_by=self.user,
        )

        class RemoteStorageStub:
            def exists(self, *_args, **_kwargs):
                raise AssertionError("Remote storage exists() should not be probed on detail serialization")

        url = reverse("customer-applications-detail", kwargs={"pk": self.application.pk})
        with self.settings(DEFAULT_SPONSOR_PASSPORT_FILE_PATH="default_documents/default_sponsor_document.pdf"), patch(
            "customer_applications.hooks.ktp_sponsor.default_storage",
            RemoteStorageStub(),
        ):
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        payload = response.json()
        ktp_docs = [doc for doc in payload["documents"] if doc["docType"]["name"] == "KTP Sponsor"]
        self.assertEqual(len(ktp_docs), 1)
        action_names = [action["name"] for action in ktp_docs[0]["extraActions"]]
        self.assertIn("upload_default", action_names)

    def test_create_application_via_api_creates_documents_and_workflow(self):
        # Create a product with required docs and a task
        product = Product.objects.create(
            name="Test Product", code="TP-1", product_type="visa", required_documents="Passport"
        )
        task = product.tasks.create(step=1, name="Collect Docs", duration=2, duration_is_business_days=True)
        self.customer = Customer.objects.create(
            customer_type="person", first_name="Bob", last_name="Builder", active=True
        )
        payload = {
            "customer": self.customer.id,
            "product": product.id,
            "doc_date": timezone.now().date().isoformat(),
            "notes": "API created",
            "document_types": [{"doc_type_id": self.doc_type.id, "required": True}],
        }
        url = reverse("customer-applications-list")
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        data = response.json()
        app = DocApplication.objects.get(pk=data["id"])
        self.assertEqual(app.product.id, product.id)
        # a workflow should be created
        self.assertTrue(app.workflows.exists())

    def test_advance_workflow_endpoint(self):
        # Setup with two tasks
        product = Product.objects.create(
            name="Test Product 2", code="TP-2", product_type="visa", required_documents="Passport"
        )
        product.tasks.create(step=1, name="Step1", duration=1, duration_is_business_days=True)
        product.tasks.create(step=2, name="Step2", duration=1, duration_is_business_days=True)
        app = DocApplication.objects.create(
            customer=self.customer, product=product, doc_date=timezone.now().date(), created_by=self.user
        )
        # create initial workflow for step 1
        from customer_applications.models.doc_workflow import DocWorkflow

        t1 = product.tasks.get(step=1)
        wf = DocWorkflow(
            start_date=timezone.now().date(),
            task=t1,
            doc_application=app,
            created_by=self.user,
            status=DocWorkflow.STATUS_PENDING,
        )
        wf.due_date = wf.calculate_workflow_due_date()
        wf.save()
        url = reverse("customer-applications-advance-workflow", kwargs={"pk": app.id})

        # Workflow progression is independent from document collection completion.
        response = self.client.post(url)
        self.assertEqual(response.status_code, 200)
        app.refresh_from_db()
        self.assertTrue(app.workflows.filter(status=DocWorkflow.STATUS_PENDING).exists())

    def test_document_update_accepts_metadata(self):
        url = reverse("documents-detail", kwargs={"pk": self.document.pk})
        payload = {
            "doc_number": "A123456",
            "metadata": {"number": "A123456"},
        }
        response = self.client.patch(url, payload, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.doc_number, "A123456")
        self.assertEqual(self.document.metadata.get("number"), "A123456")

    @patch("api.views.run_document_validation")
    def test_document_update_accepts_boolean_validate_with_ai_flag(self, run_validation_mock):
        url = reverse("documents-detail", kwargs={"pk": self.document.pk})
        payload = {
            "doc_number": "B987654",
            "validate_with_ai": True,
        }

        response = self.client.patch(url, payload, content_type="application/json")

        self.assertEqual(response.status_code, 200)
        self.document.refresh_from_db()
        self.assertEqual(self.document.doc_number, "B987654")
        run_validation_mock.assert_not_called()

    def test_application_detail_documents_ordering(self):
        # Create a product with specific document order
        product = Product.objects.create(
            name="Ordered Product",
            code="ORD-1",
            product_type="visa",
            required_documents="Passport, ID Card",
            optional_documents="Photo",
        )

        doc_type_id_card = DocumentType.objects.create(name="ID Card")
        doc_type_photo = DocumentType.objects.create(name="Photo")
        doc_type_other = DocumentType.objects.create(name="Other")

        app = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

        # Create docs in wrong order
        Document.objects.create(doc_application=app, doc_type=doc_type_other, created_by=self.user)
        Document.objects.create(doc_application=app, doc_type=doc_type_photo, created_by=self.user)
        Document.objects.create(doc_application=app, doc_type=doc_type_id_card, created_by=self.user)
        Document.objects.create(doc_application=app, doc_type=self.doc_type, created_by=self.user)  # Passport

        url = reverse("customer-applications-detail", kwargs={"pk": app.pk})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()

        docs = data["documents"]
        self.assertEqual(len(docs), 4)
        self.assertEqual(docs[0]["docType"]["name"], "Passport")
        self.assertEqual(docs[1]["docType"]["name"], "ID Card")
        self.assertEqual(docs[2]["docType"]["name"], "Photo")
        self.assertEqual(docs[3]["docType"]["name"], "Other")

    def test_application_detail_query_budget(self):
        from customer_applications.models.doc_workflow import DocWorkflow

        product = Product.objects.create(
            name="Workflow Product",
            code="WF-1",
            product_type="visa",
            required_documents="Passport",
        )

        tasks = [
            product.tasks.create(step=1, name="Step 1", duration=1, duration_is_business_days=True),
            product.tasks.create(step=2, name="Step 2", duration=1, duration_is_business_days=True),
            product.tasks.create(step=3, name="Step 3", duration=1, duration_is_business_days=True),
            product.tasks.create(step=4, name="Step 4", duration=1, duration_is_business_days=True, last_step=True),
        ]

        app = DocApplication.objects.create(
            customer=self.customer,
            product=product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

        Document.objects.create(
            doc_application=app,
            doc_type=self.doc_type,
            required=True,
            completed=True,
            created_by=self.user,
        )

        for task in tasks:
            workflow = DocWorkflow(
                doc_application=app,
                task=task,
                start_date=timezone.now().date(),
                status=DocWorkflow.STATUS_COMPLETED if task.step < 4 else DocWorkflow.STATUS_PROCESSING,
                created_by=self.user,
            )
            workflow.due_date = workflow.calculate_workflow_due_date()
            workflow.save()

        url = reverse("customer-applications-detail", kwargs={"pk": app.pk})
        with CaptureQueriesContext(connection) as queries:
            response = self.client.get(url)

        self.assertEqual(response.status_code, 200)
        self.assertLessEqual(
            len(queries),
            14,
            f"GET {url} exceeded query budget: {len(queries)} queries",
        )


class ProductApiTestCase(TestCase):
    def setUp(self):
        from django.core.cache import cache

        cache.clear()
        User = get_user_model()
        self.user = User.objects.create_superuser(
            username="productadmin", email="product@example.com", password="password"
        )
        # Ensure tests that require superuser auth are authenticated
        self.client.force_login(self.user)
        self.required_doc = DocumentType.objects.create(name="Passport", is_in_required_documents=True)
        self.optional_doc = DocumentType.objects.create(name="Bank Statement", is_in_required_documents=False)

    def test_propose_invoice_number_endpoint(self):
        # Ensure the propose endpoint returns the next invoice number for a given date
        self.client.force_login(self.user)
        year = 2026
        # The API call itself increments the sequence in cache
        url = reverse("invoices-propose") + f"?invoice_date={year}-01-01"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Accept camelCase or snake_case
        self.assertTrue("invoice_no" in data or "invoiceNo" in data)
        value = data.get("invoice_no") or data.get("invoiceNo")
        # Basic sanity: value should be an integer for the requested year
        self.assertIsInstance(value, int)
        self.assertTrue(str(value).startswith(str(year)))

    def test_create_invoice_via_api(self):
        # Test that creating an invoice via the API with an application works
        self.client.force_login(self.user)
        # Create a customer and product and application
        customer = Customer.objects.create(customer_type="person", first_name="API", last_name="User", active=True)
        product = Product.objects.create(
            name="Test Product", code="TP-100", product_type="visa", required_documents="Passport"
        )
        application = DocApplication.objects.create(
            customer=customer, product=product, doc_date=timezone.now().date(), created_by=self.user
        )

        payload = {
            "customer": customer.id,
            "invoice_date": timezone.now().date().isoformat(),
            "due_date": timezone.now().date().isoformat(),
            # Don’t set invoiceNo to allow proposal
            "invoice_applications": [{"customer_application": application.id, "amount": "1000.00"}],
        }

        url = reverse("invoices-list")
        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertIn(response.status_code, (200, 201))
        data = response.json()
        # Check invoice created and includes applications
        self.assertTrue("id" in data)
        inv = Invoice.objects.get(pk=data["id"])
        self.assertEqual(inv.customer_id, customer.id)
        self.assertEqual(inv.invoice_applications.count(), 1)

    def test_product_create_with_tasks_and_documents(self):
        url = reverse("products-list")
        payload = {
            "name": "Visa Extension",
            "code": "VISA-EXT",
            "description": "Extension service",
            "productType": "visa",
            "basePrice": "1500000.00",
            "retailPrice": "1750000.00",
            "validity": 30,
            "documentsMinValidity": 180,
            "requiredDocumentIds": [self.required_doc.id],
            "optionalDocumentIds": [self.optional_doc.id],
            "tasks": [
                {
                    "step": 1,
                    "name": "Collect Documents",
                    "description": "Gather required docs",
                    "cost": "0.00",
                    "duration": 5,
                    "durationIsBusinessDays": True,
                    "addTaskToCalendar": True,
                    "notifyDaysBefore": 2,
                    "notifyCustomer": False,
                    "lastStep": False,
                },
                {
                    "step": 2,
                    "name": "Submit Application",
                    "description": "Submit to immigration",
                    "cost": "500000.00",
                    "duration": 3,
                    "durationIsBusinessDays": True,
                    "addTaskToCalendar": True,
                    "notifyDaysBefore": 1,
                    "notifyCustomer": True,
                    "lastStep": True,
                },
            ],
        }

        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 201)
        product = Product.objects.get(code="VISA-EXT")
        self.assertEqual(str(product.retail_price), "1750000.00")
        self.assertEqual(product.required_documents, "Passport")
        self.assertEqual(product.optional_documents, "Bank Statement")
        self.assertEqual(product.tasks.count(), 2)
        self.assertFalse(product.tasks.get(step=1).notify_customer)
        self.assertTrue(product.tasks.get(step=2).notify_customer)

    def test_product_update_reconciles_tasks(self):
        product = Product.objects.create(
            name="Tourist Visa",
            code="TOUR-1",
            product_type="visa",
            required_documents="Passport",
        )
        task_one = product.tasks.create(
            step=1,
            name="Collect Documents",
            description="",
            cost=0,
            duration=2,
            duration_is_business_days=True,
            notify_days_before=1,
            last_step=False,
        )
        product.tasks.create(
            step=2,
            name="Submit",
            description="",
            cost=0,
            duration=1,
            duration_is_business_days=True,
            notify_days_before=0,
            last_step=True,
        )

        url = reverse("products-detail", kwargs={"pk": product.id})
        payload = {
            "name": "Tourist Visa Updated",
            "code": "TOUR-1",
            "productType": "visa",
            "basePrice": "1200000.00",
            "retailPrice": "1500000.00",
            "requiredDocumentIds": [self.required_doc.id],
            "optionalDocumentIds": [],
            "tasks": [
                {
                    "id": task_one.id,
                    "step": 1,
                    "name": "Collect Docs",
                    "description": "Updated",
                    "cost": "0.00",
                    "duration": 4,
                    "durationIsBusinessDays": True,
                    "addTaskToCalendar": True,
                    "notifyDaysBefore": 1,
                    "notifyCustomer": True,
                    "lastStep": True,
                }
            ],
        }
        response = self.client.put(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 200)
        product.refresh_from_db()
        self.assertEqual(str(product.retail_price), "1500000.00")
        self.assertEqual(product.tasks.count(), 1)
        self.assertEqual(product.tasks.first().name, "Collect Docs")
        self.assertTrue(product.tasks.first().notify_customer)

    def test_product_create_rejects_retail_price_below_base_price(self):
        url = reverse("products-list")
        payload = {
            "name": "Invalid Retail",
            "code": "INVALID-RETAIL",
            "productType": "visa",
            "basePrice": "1000000.00",
            "retailPrice": "900000.00",
        }

        response = self.client.post(url, data=json.dumps(payload), content_type="application/json")
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("errors", body)
        self.assertTrue("retailPrice" in body["errors"] or "retail_price" in body["errors"])

    def test_product_can_delete_endpoint(self):
        self.client.force_login(self.user)
        product = Product.objects.create(name="Simple", code="S-1", product_type="other")
        url = reverse("products-can-delete", kwargs={"pk": product.id})
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        payload = response.json()
        # Accept either snake_case or camelCase keys
        self.assertTrue("can_delete" in payload or "canDelete" in payload)

    def test_product_search_includes_description(self):
        """Ensure the API search endpoint also matches text found in the product description."""
        # Create a product with a distinctive word in the description
        product = Product.objects.create(
            name="Desc Search",
            code="DESC-1",
            product_type="visa",
            description="This description contains the uniquephrase123 for testing",
        )
        url = reverse("products-list") + "?search=uniquephrase123"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Should find at least one product and it should be our product
        results = data.get("results", [])
        self.assertGreater(len(results), 0)
        self.assertTrue(any(item.get("code") == "DESC-1" for item in results))

    def test_document_type_deprecation_requires_confirmation_and_cascades_products(self):
        document_type = DocumentType.objects.create(name="KITAS Sponsor Letter")
        product = Product.objects.create(
            name="KITAS Service",
            code="KITAS-SRV",
            product_type="visa",
            required_documents=document_type.name,
        )

        url = reverse("document-types-detail", kwargs={"pk": document_type.id})

        response = self.client.patch(url, data=json.dumps({"deprecated": True}), content_type="application/json")
        self.assertEqual(response.status_code, 409)
        body = response.json()
        self.assertEqual(body.get("code"), "deprecated_products_confirmation_required")
        self.assertTrue(body.get("relatedProducts"))

        response = self.client.patch(
            f"{url}?deprecate_related_products=true",
            data=json.dumps({"deprecated": True}),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 200)

        document_type.refresh_from_db()
        product.refresh_from_db()
        self.assertTrue(document_type.deprecated)
        self.assertTrue(product.deprecated)

    def test_products_list_hides_deprecated_by_default(self):
        active_product = Product.objects.create(name="Active", code="ACTIVE-1", product_type="other")
        deprecated_product = Product.objects.create(
            name="Deprecated",
            code="DEPR-1",
            product_type="other",
            deprecated=True,
        )

        url = reverse("products-list")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        visible_codes = {item.get("code") for item in response.json().get("results", [])}
        self.assertIn(active_product.code, visible_codes)
        self.assertNotIn(deprecated_product.code, visible_codes)

        response = self.client.get(f"{url}?hide_deprecated=false")
        self.assertEqual(response.status_code, 200)
        visible_codes = {item.get("code") for item in response.json().get("results", [])}
        self.assertIn(active_product.code, visible_codes)
        self.assertIn(deprecated_product.code, visible_codes)

    def test_invoice_create_rejects_applications_with_deprecated_products(self):
        customer = Customer.objects.create(customer_type="person", first_name="Dep", last_name="Invoice")
        deprecated_product = Product.objects.create(
            name="Deprecated Product",
            code="DEP-INV",
            product_type="visa",
            deprecated=True,
        )
        app = DocApplication.objects.create(
            customer=customer,
            product=deprecated_product,
            doc_date=timezone.now().date(),
            created_by=self.user,
        )

        payload = {
            "customer": customer.id,
            "invoice_date": timezone.now().date().isoformat(),
            "due_date": timezone.now().date().isoformat(),
            "invoice_applications": [{"customer_application": app.id, "amount": "1000.00"}],
        }
        response = self.client.post(
            reverse("invoices-list"),
            data=json.dumps(payload),
            content_type="application/json",
        )
        self.assertEqual(response.status_code, 400)
        body = response.json()
        self.assertIn("errors", body)


class UserSettingsApiTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_user(username="settest", email="u@example.com", password="password")

    def test_get_user_settings_requires_authentication(self):
        url = reverse("user-settings-me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 401)

    def test_get_and_patch_user_settings(self):
        self.client.force_login(self.user)
        url = reverse("user-settings-me")
        response = self.client.get(url)
        self.assertEqual(response.status_code, 200)
        data = response.json()
        # Accept either snake_case or camelCase keys
        self.assertTrue("theme" in data)
        self.assertTrue("dark_mode" in data or "darkMode" in data)

        # Patch theme and dark_mode
        patch = {"theme": "starlight", "dark_mode": True}
        response = self.client.patch(url, data=patch, content_type="application/json")
        self.assertEqual(response.status_code, 200)
        data = response.json()
        self.assertEqual(data.get("theme"), "starlight")
        self.assertTrue((data.get("dark_mode") is True) or (data.get("darkMode") is True))


class InvoiceDownloadAPITestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.user = User.objects.create_superuser(username="invadmin", email="inv@example.com", password="password")
        self.client.force_login(self.user)
        self.customer = Customer.objects.create(customer_type="person", first_name="Inv", last_name="User", active=True)
        self.invoice = Invoice.objects.create(
            customer=self.customer,
            invoice_date=timezone.now().date(),
            due_date=timezone.now().date(),
            invoice_no=20260001,
        )

    def test_invoice_download_no_format_default_docx(self):
        # Default should be docx
        url = reverse("invoices-download", kwargs={"pk": self.invoice.pk})
        response = self.client.get(url)
        # We expect 200 if templates are found, or at least not 404
        self.assertNotEqual(response.status_code, 404)
        if response.status_code == 200:
            self.assertEqual(
                response["Content-Type"], "application/vnd.openxmlformats-officedocument.wordprocessingml.document"
            )

    def test_invoice_download_reserved_keyword_404(self):
        # Verify that ?format=docx returns 404 due to DRF collision
        url = reverse("invoices-download", kwargs={"pk": self.invoice.pk}) + "?format=docx"
        response = self.client.get(url)
        self.assertEqual(response.status_code, 404)

    def test_invoice_download_file_format_parameter(self):
        # Verify that ?file_format=docx returns 200 (or at least not 404)
        url = reverse("invoices-download", kwargs={"pk": self.invoice.pk}) + "?file_format=docx"
        response = self.client.get(url)
        self.assertNotEqual(response.status_code, 404)


class HolidayAPIPermissionsTestCase(TestCase):
    def setUp(self):
        User = get_user_model()
        self.superuser = User.objects.create_superuser(
            username="holidayadmin", email="holidayadmin@example.com", password="password"
        )
        self.user = User.objects.create_user(
            username="holidayuser", email="holidayuser@example.com", password="password"
        )
        self.holiday = Holiday.objects.create(
            name="Independence Day", date=datetime.date(2025, 8, 17), country="Indonesia"
        )

    def test_non_superuser_can_list_and_retrieve_holidays(self):
        self.client.force_login(self.user)

        list_response = self.client.get(reverse("holidays-list"))
        self.assertEqual(list_response.status_code, 200)
        self.assertEqual(len(list_response.json()), 1)

        detail_response = self.client.get(reverse("holidays-detail", args=[self.holiday.id]))
        self.assertEqual(detail_response.status_code, 200)
        self.assertEqual(detail_response.json()["name"], "Independence Day")

    def test_non_superuser_cannot_create_holiday(self):
        self.client.force_login(self.user)
        response = self.client.post(
            reverse("holidays-list"), {"name": "Nyepi", "date": "2025-03-29", "country": "Indonesia"}
        )
        self.assertEqual(response.status_code, 403)

    def test_superuser_can_create_holiday(self):
        self.client.force_login(self.superuser)
        response = self.client.post(
            reverse("holidays-list"), {"name": "Nyepi", "date": "2025-03-29", "country": "Indonesia"}
        )
        self.assertEqual(response.status_code, 201)
