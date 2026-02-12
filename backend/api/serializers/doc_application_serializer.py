import os

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.doc_workflow_serializer import DocWorkflowSerializer, TaskSerializer
from api.serializers.document_serializer import DocumentSerializer
from api.serializers.product_serializer import ProductSerializer
from customer_applications.models import DocApplication
from rest_framework import serializers


class DocApplicationSerializer(serializers.ModelSerializer):
    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "add_deadlines_to_calendar",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["str_field"] = str(instance)
        return representation


class DocApplicationSerializerWithRelations(serializers.ModelSerializer):
    has_invoice = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    ready_for_invoice = serializers.SerializerMethodField()
    can_force_close = serializers.SerializerMethodField()

    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "add_deadlines_to_calendar",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "has_invoice",
            "invoice_id",
            "ready_for_invoice",
            "can_force_close",
        ]
        read_only_fields = ["created_at", "updated_at"]

    def get_has_invoice(self, instance) -> bool:
        """Check if the application has an invoice."""
        return instance.has_invoice()

    def get_invoice_id(self, instance) -> int | None:
        """Get the invoice ID if it exists."""
        invoice = instance.get_invoice()
        return invoice.id if invoice else None

    def get_ready_for_invoice(self, instance) -> bool:
        """Check if application is ready for invoicing.

        Ready if all required documents are completed OR if the application
        has been marked as completed (e.g. force closed).
        """
        if instance.status == DocApplication.STATUS_COMPLETED:
            return True
        return instance.total_required_documents == instance.completed_required_documents

    def get_can_force_close(self, instance) -> bool:
        """Return True if the current user can force close this application."""
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return False
        return (
            request.user.has_perm("customer_applications.change_docapplication")
            and instance.status != DocApplication.STATUS_COMPLETED
        )

    def to_representation(self, instance):
        representation = super().to_representation(instance)
        representation["product"] = ProductSerializer(instance.product).data
        representation["customer"] = CustomerSerializer(instance.customer).data
        representation["str_field"] = str(instance)
        return representation


class DocApplicationInvoiceSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    customer = CustomerSerializer(read_only=True)
    str_field = serializers.SerializerMethodField()

    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "add_deadlines_to_calendar",
            "status",
            "notes",
            "str_field",
        ]
        read_only_fields = fields

    def get_str_field(self, instance) -> str:
        return str(instance)


class DocApplicationDetailSerializer(serializers.ModelSerializer):
    product = ProductSerializer(read_only=True)
    customer = CustomerSerializer(read_only=True)
    documents = DocumentSerializer(many=True, read_only=True, source="ordered_documents")
    workflows = DocWorkflowSerializer(many=True, read_only=True)
    str_field = serializers.SerializerMethodField()
    is_document_collection_completed = serializers.BooleanField(read_only=True)
    is_application_completed = serializers.BooleanField(read_only=True)
    has_next_task = serializers.BooleanField(read_only=True)
    next_task = TaskSerializer(read_only=True)
    has_invoice = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    can_force_close = serializers.SerializerMethodField()

    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "add_deadlines_to_calendar",
            "notify_customer_too",
            "notify_customer_channel",
            "status",
            "notes",
            "created_at",
            "updated_at",
            "created_by",
            "updated_by",
            "documents",
            "workflows",
            "is_document_collection_completed",
            "is_application_completed",
            "has_next_task",
            "next_task",
            "has_invoice",
            "invoice_id",
            "str_field",
            "can_force_close",
        ]
        read_only_fields = fields

    def get_str_field(self, instance) -> str:
        return str(instance)

    def get_has_invoice(self, instance) -> bool:
        return instance.has_invoice()

    def get_invoice_id(self, instance) -> int | None:
        invoice = instance.get_invoice()
        return invoice.id if invoice else None

    def get_can_force_close(self, instance) -> bool:
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return False
        return (
            request.user.has_perm("customer_applications.change_docapplication")
            and instance.status != DocApplication.STATUS_COMPLETED
        )


class DocApplicationCreateUpdateSerializer(serializers.ModelSerializer):
    document_types = serializers.ListField(child=serializers.DictField(), write_only=True, required=False)

    class Meta:
        model = DocApplication
        fields = [
            "id",
            "customer",
            "product",
            "doc_date",
            "due_date",
            "notes",
            "add_deadlines_to_calendar",
            "notify_customer_too",
            "notify_customer_channel",
            "document_types",
        ]
        read_only_fields = ["id"]

    def validate(self, attrs):
        doc_date = attrs.get("doc_date") or getattr(self.instance, "doc_date", None)
        due_date = attrs.get("due_date") or getattr(self.instance, "due_date", None)
        if due_date and doc_date and due_date < doc_date:
            raise serializers.ValidationError({"due_date": "Due date cannot be before document date."})

        notify_customer_too = attrs.get("notify_customer_too")
        if notify_customer_too is None and self.instance is not None:
            notify_customer_too = self.instance.notify_customer_too
        notify_customer_channel = attrs.get("notify_customer_channel")
        if notify_customer_channel is None and self.instance is not None:
            notify_customer_channel = self.instance.notify_customer_channel

        customer = attrs.get("customer") or getattr(self.instance, "customer", None)
        if notify_customer_too:
            if not notify_customer_channel:
                raise serializers.ValidationError({"notify_customer_channel": "Select a notification channel."})
            if notify_customer_channel == "whatsapp" and not getattr(customer, "whatsapp", None):
                raise serializers.ValidationError({"notify_customer_channel": "Customer has no WhatsApp number."})
            if notify_customer_channel == "email" and not getattr(customer, "email", None):
                raise serializers.ValidationError({"notify_customer_channel": "Customer has no email."})

        return attrs

    def create(self, validated_data):
        from customer_applications.models.doc_workflow import DocWorkflow
        from customer_applications.models.document import Document
        from django.core.files import File
        from django.core.files.storage import default_storage
        from django.utils import timezone
        from products.models.document_type import DocumentType
        from products.models.task import Task

        document_types = validated_data.pop("document_types", [])
        user = self.context["request"].user

        # Create application
        if not validated_data.get("due_date"):
            product = validated_data.get("product")
            doc_date = validated_data.get("doc_date")
            next_calendar_task = (
                product.tasks.filter(add_task_to_calendar=True).order_by("step").first() if product else None
            )
            if next_calendar_task:
                from core.utils.dateutils import calculate_due_date

                validated_data["due_date"] = calculate_due_date(
                    doc_date, next_calendar_task.duration, next_calendar_task.duration_is_business_days
                )
            else:
                validated_data["due_date"] = doc_date

        validated_data["created_by"] = user
        application = DocApplication.objects.create(**validated_data)

        # Pre-check if passport can be auto-imported to avoid creating placeholder
        has_auto_passport = self._can_auto_import_passport(application)

        # Create provided documents
        for dt in document_types:
            doc_type_id = dt.get("doc_type_id") or dt.get("id")
            required = dt.get("required", True)
            try:
                doc_type = DocumentType.objects.get(pk=doc_type_id)
            except DocumentType.DoesNotExist:
                raise serializers.ValidationError({"document_types": f"Invalid document type id: {doc_type_id}"})

            # Skip creating placeholder if passport will be auto-imported
            if doc_type.name == "Passport" and has_auto_passport:
                continue

            doc = Document(
                doc_application=application,
                doc_type=doc_type,
                required=required,
                created_by=user,
                created_at=timezone.now(),
                updated_at=timezone.now(),
            )
            doc.save()

        # Create the first workflow step (step 1) if it exists
        task = Task.objects.filter(product=application.product, step=1).first()
        if task:
            step1 = DocWorkflow(
                start_date=timezone.now().date(),
                task=task,
                doc_application=application,
                created_by=user,
                status=DocWorkflow.STATUS_PENDING,
            )
            step1.due_date = step1.calculate_workflow_due_date()
            step1.save()

        # Perform auto-import
        if has_auto_passport:
            self._auto_import_passport(application, user)

        self._trigger_immediate_due_tomorrow_notification(application)
        return application

    def update(self, instance, validated_data):
        from customer_applications.models.document import Document
        from django.utils import timezone
        from products.models.document_type import DocumentType

        document_types = validated_data.pop("document_types", None)
        application = super().update(instance, validated_data)

        if document_types is not None:
            desired: dict[int, bool] = {}
            for dt in document_types:
                doc_type_id = dt.get("doc_type_id") or dt.get("id")
                if not doc_type_id:
                    continue
                desired[int(doc_type_id)] = bool(dt.get("required", True))

            existing_docs = Document.objects.filter(doc_application=application)
            existing_by_type = {doc.doc_type_id: doc for doc in existing_docs}

            # Remove only pending placeholder docs that are no longer requested.
            for doc in existing_docs:
                if doc.doc_type_id not in desired and not doc.completed:
                    doc.delete()

            user = self.context.get("request").user if self.context.get("request") else None
            for doc_type_id, required in desired.items():
                existing = existing_by_type.get(doc_type_id)
                if existing:
                    if existing.required != required:
                        existing.required = required
                        existing.updated_by = user
                        existing.updated_at = timezone.now()
                        existing.save(update_fields=["required", "updated_by", "updated_at"])
                    continue
                try:
                    doc_type = DocumentType.objects.get(pk=doc_type_id)
                except DocumentType.DoesNotExist:
                    raise serializers.ValidationError({"document_types": f"Invalid document type id: {doc_type_id}"})
                Document.objects.create(
                    doc_application=application,
                    doc_type=doc_type,
                    required=required,
                    created_by=user,
                    updated_by=user,
                )

        self._trigger_immediate_due_tomorrow_notification(application)
        return application

    def _trigger_immediate_due_tomorrow_notification(self, application):
        from customer_applications.tasks import send_due_tomorrow_customer_notifications
        from django.utils import timezone

        send_due_tomorrow_customer_notifications(
            now=timezone.now(),
            application_ids=[application.id],
            immediate=True,
        )

    def _can_auto_import_passport(self, application) -> bool:
        """Check if passport can be auto-imported for this application."""
        from customer_applications.models.document import Document
        from django.core.files.storage import default_storage
        from products.models.document_type import DocumentType

        try:
            passport_doc_type = DocumentType.objects.get(name="Passport")
        except DocumentType.DoesNotExist:
            return False

        # Check if product has Passport in required or optional documents
        product = application.product
        all_docs = (product.required_documents or "") + "," + (product.optional_documents or "")
        doc_names = [d.strip() for d in all_docs.split(",") if d.strip()]

        if passport_doc_type.name not in doc_names:
            return False

        # Option 1: Customer has passport file
        customer = application.customer
        if customer.passport_file and customer.passport_number:
            if default_storage.exists(customer.passport_file.name):
                return True

        # Option 2: Previous valid passport document exists
        previous_doc = (
            Document.objects.filter(doc_application__customer=customer, doc_type=passport_doc_type)
            .exclude(doc_application=application)
            .order_by("-created_at")
            .first()
        )
        if previous_doc and previous_doc.file and not previous_doc.is_expired:
            return True

        return False

    def _auto_import_passport(self, application, user):
        """Replicates legacy auto-import logic from DocApplicationCreateView."""
        from core.models.country_code import CountryCode
        from customer_applications.models.document import Document, get_upload_to
        from django.core.files import File
        from django.core.files.storage import default_storage
        from django.utils import timezone
        from products.models.document_type import DocumentType

        passport_doc_type = DocumentType.objects.get(name="Passport")
        customer = application.customer

        # Helper for detail string
        def fmt_date(d):
            if not d:
                return None
            return d.isoformat() if hasattr(d, "isoformat") else str(d)

        # 1. Try customer profile first
        if customer.passport_file and customer.passport_number and default_storage.exists(customer.passport_file.name):
            try:
                # Extract metadata like in legacy view, prioritizing model fields over passport_metadata
                mrz_meta = customer.passport_metadata or {}

                def get_val(attr, meta_key):
                    val = getattr(customer, attr, None)
                    return val if val else mrz_meta.get(meta_key)

                trimmed_metadata = {
                    "number": customer.passport_number,
                    "issue_date_yyyy_mm_dd": fmt_date(get_val("passport_issue_date", "issue_date_yyyy_mm_dd")),
                    "expiration_date_yyyy_mm_dd": fmt_date(
                        get_val("passport_expiration_date", "expiration_date_yyyy_mm_dd")
                    ),
                    "date_of_birth_yyyy_mm_dd": fmt_date(get_val("birthdate", "date_of_birth_yyyy_mm_dd")),
                    "birth_place": get_val("birth_place", "birth_place"),
                    "sex": customer.gender or mrz_meta.get("sex") or mrz_meta.get("mrz_sex"),
                }

                alpha3 = customer.nationality.alpha3_code if customer.nationality else mrz_meta.get("nationality")

                country_obj = CountryCode.objects.get_country_code_by_alpha3_code(alpha3) if alpha3 else None
                country_name = country_obj.country if country_obj else alpha3
                trimmed_metadata["nationality"] = country_name
                trimmed_metadata["country"] = mrz_meta.get("country") or mrz_meta.get("issuing_country") or country_name

                details_parts = []
                if customer.birth_place:
                    details_parts.append(f"Birth Place: {customer.birth_place}")
                if customer.birthdate:
                    details_parts.append(f"Birthdate: {customer.birthdate}")
                if country_name:
                    details_parts.append(f"Nationality: {country_name}")
                if customer.passport_issue_date:
                    details_parts.append(f"Issue Date: {customer.passport_issue_date}")

                doc = Document(
                    doc_application=application,
                    doc_type=passport_doc_type,
                    doc_number=customer.passport_number,
                    expiration_date=customer.passport_expiration_date,
                    details="\n".join(details_parts),
                    ocr_check=bool(customer.passport_metadata),
                    metadata=trimmed_metadata,
                    completed=True,
                    required=True,  # Passports are usually required if present
                    created_by=user,
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                )

                with customer.passport_file.open("rb") as f:
                    file = File(f)
                    file_name = os.path.basename(customer.passport_file.name)
                    upload_path = get_upload_to(doc, file_name)
                    saved_path = default_storage.save(upload_path, file)
                    doc.file = saved_path
                    doc.file_link = default_storage.url(saved_path)
                    doc.save()
                return
            except Exception:
                pass

        # 2. Try previous application
        previous_doc = (
            Document.objects.filter(doc_application__customer=customer, doc_type=passport_doc_type)
            .exclude(doc_application=application)
            .order_by("-created_at")
            .first()
        )
        if previous_doc and previous_doc.file and not previous_doc.is_expired:
            try:
                new_doc = Document(
                    doc_application=application,
                    doc_type=passport_doc_type,
                    file=previous_doc.file,
                    file_link=previous_doc.file_link,
                    doc_number=previous_doc.doc_number,
                    expiration_date=previous_doc.expiration_date,
                    ocr_check=previous_doc.ocr_check,
                    metadata=previous_doc.metadata,
                    completed=previous_doc.completed,
                    required=previous_doc.required,
                    details=previous_doc.details,
                    created_by=user,
                    created_at=timezone.now(),
                    updated_at=timezone.now(),
                )
                new_doc.save()
            except Exception:
                pass
