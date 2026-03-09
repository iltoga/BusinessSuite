import os

from api.serializers.customer_serializer import CustomerSerializer
from api.serializers.doc_workflow_serializer import DocWorkflowSerializer, TaskSerializer
from api.serializers.document_serializer import DocumentSerializer
from api.serializers.product_serializer import ProductSerializer
from customer_applications.models import DocApplication
from customer_applications.services.stay_permit_submission_window_service import StayPermitSubmissionWindowService
from django.core.exceptions import ValidationError as DjangoValidationError
from invoices.models.invoice import InvoiceApplication
from products.models.document_type import DocumentType
from rest_framework import serializers


def is_ready_for_invoice(instance: DocApplication) -> bool:
    product = getattr(instance, "product", None)
    if not product:
        return False
    if getattr(product, "deprecated", False):
        return False
    if not getattr(product, "uses_customer_app_workflow", True):
        return False
    if instance.status in (DocApplication.STATUS_COMPLETED, DocApplication.STATUS_REJECTED):
        return True

    total_required_documents = getattr(instance, "total_required_documents", None)
    completed_required_documents = getattr(instance, "completed_required_documents", None)
    if total_required_documents is not None and completed_required_documents is not None:
        return total_required_documents == completed_required_documents

    completion_value = getattr(instance, "is_document_collection_completed", None)
    if callable(completion_value):
        return bool(completion_value())
    if completion_value is not None:
        return bool(completion_value)
    return False


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
        return is_ready_for_invoice(instance)

    def get_can_force_close(self, instance) -> bool:
        """Return True if the current user can force close this application."""
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return False
        return request.user.has_perm("customer_applications.change_docapplication") and instance.status not in (
            DocApplication.STATUS_COMPLETED,
            DocApplication.STATUS_REJECTED,
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


class CustomerUninvoicedApplicationSerializer(DocApplicationInvoiceSerializer):
    status_display = serializers.CharField(source="get_status_display", read_only=True)
    product_type_display = serializers.SerializerMethodField()
    has_invoice = serializers.SerializerMethodField()
    invoice_id = serializers.SerializerMethodField()
    is_document_collection_completed = serializers.BooleanField(read_only=True)
    ready_for_invoice = serializers.SerializerMethodField()

    class Meta(DocApplicationInvoiceSerializer.Meta):
        fields = DocApplicationInvoiceSerializer.Meta.fields + [
            "status_display",
            "product_type_display",
            "has_invoice",
            "invoice_id",
            "is_document_collection_completed",
            "ready_for_invoice",
        ]
        read_only_fields = fields

    def get_product_type_display(self, instance) -> str:
        return instance.product.get_product_type_display() if instance.product else ""

    def get_has_invoice(self, instance) -> bool:
        return instance.has_invoice()

    def get_invoice_id(self, instance) -> int | None:
        invoice = instance.get_invoice()
        return invoice.id if invoice else None

    def get_ready_for_invoice(self, instance) -> bool:
        return is_ready_for_invoice(instance)


class CustomerApplicationHistorySerializer(CustomerUninvoicedApplicationSerializer):
    payment_status = serializers.SerializerMethodField()
    payment_status_display = serializers.SerializerMethodField()
    invoice_status = serializers.SerializerMethodField()
    invoice_status_display = serializers.SerializerMethodField()

    class Meta(CustomerUninvoicedApplicationSerializer.Meta):
        fields = CustomerUninvoicedApplicationSerializer.Meta.fields + [
            "payment_status",
            "payment_status_display",
            "invoice_status",
            "invoice_status_display",
        ]
        read_only_fields = fields

    def _latest_invoice_application(self, instance):
        cache_attr = "_latest_invoice_application_cache"
        if hasattr(instance, cache_attr):
            return getattr(instance, cache_attr)

        # Use prefetched invoice_applications when available; fallback to a targeted query.
        invoice_applications = list(instance.invoice_applications.all())
        latest = (
            max(invoice_applications, key=lambda invoice_application: invoice_application.id)
            if invoice_applications
            else None
        )
        setattr(instance, cache_attr, latest)
        return latest

    def get_has_invoice(self, instance) -> bool:
        return self._latest_invoice_application(instance) is not None

    def get_invoice_id(self, instance) -> int | None:
        latest = self._latest_invoice_application(instance)
        return latest.invoice_id if latest else None

    def get_payment_status(self, instance) -> str:
        latest = self._latest_invoice_application(instance)
        if not latest:
            return "uninvoiced"
        if latest.status == InvoiceApplication.PAID:
            return "paid"
        return "pending_payment"

    def get_payment_status_display(self, instance) -> str:
        status = self.get_payment_status(instance)
        if status == "paid":
            return "Paid"
        if status == "pending_payment":
            return "Pending Payment"
        return "Uninvoiced"

    def get_invoice_status(self, instance) -> str | None:
        latest = self._latest_invoice_application(instance)
        return latest.invoice.status if latest else None

    def get_invoice_status_display(self, instance) -> str:
        latest = self._latest_invoice_application(instance)
        if not latest:
            return "Uninvoiced"
        return latest.invoice.get_status_display()


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
    ready_for_invoice = serializers.SerializerMethodField()
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
            "ready_for_invoice",
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

    def get_ready_for_invoice(self, instance) -> bool:
        return is_ready_for_invoice(instance)

    def get_can_force_close(self, instance) -> bool:
        request = self.context.get("request") if hasattr(self, "context") else None
        if not request or not getattr(request, "user", None) or not request.user.is_authenticated:
            return False
        return request.user.has_perm("customer_applications.change_docapplication") and instance.status not in (
            DocApplication.STATUS_COMPLETED,
            DocApplication.STATUS_REJECTED,
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

    def _get_step_one_workflow(self, application: DocApplication):
        return (
            application.workflows.select_related("task")
            .filter(task__step=1)
            .order_by("task__step", "created_at", "id")
            .first()
        )

    def _calculate_due_date_for_doc_date(self, *, doc_date, product=None, application: DocApplication | None = None):
        if not doc_date:
            return None

        window_service = StayPermitSubmissionWindowService()
        if application is None:
            if window_service.product_requires_submission_window(product):
                return None
            next_calendar_task = product.tasks.filter(add_task_to_calendar=True).order_by("step").first() if product else None
            if next_calendar_task:
                from core.utils.dateutils import calculate_due_date

                return calculate_due_date(
                    doc_date,
                    next_calendar_task.duration,
                    next_calendar_task.duration_is_business_days,
                )
            return doc_date if product and product.tasks.exists() else None

        target = application or DocApplication(product=product, doc_date=doc_date)
        original_doc_date = getattr(target, "doc_date", None)
        original_product = getattr(target, "product", None)

        target.doc_date = doc_date
        if product is not None:
            target.product = product

        try:
            start_date = target.get_first_task_start_date()
            return target.calculate_next_calendar_due_date(start_date=start_date)
        finally:
            if application is not None:
                target.doc_date = original_doc_date
                target.product = original_product

    def _validate_single_stay_permit_document_type(self, document_types) -> None:
        if not document_types:
            return

        document_type_ids: list[int] = []
        for item in document_types:
            raw_id = item.get("doc_type_id") or item.get("id")
            try:
                document_type_ids.append(int(raw_id))
            except (TypeError, ValueError):
                continue

        if not document_type_ids:
            return

        document_types_by_id = DocumentType.objects.in_bulk(document_type_ids)
        stay_permit_names: list[str] = []
        for doc_type_id in document_type_ids:
            doc_type = document_types_by_id.get(doc_type_id)
            if doc_type and doc_type.is_stay_permit and doc_type.name not in stay_permit_names:
                stay_permit_names.append(doc_type.name)

        if len(stay_permit_names) > 1:
            raise serializers.ValidationError(
                {
                    "document_types": [
                        "Only one stay permit document type can be added to an application. "
                        f"Selected: {', '.join(stay_permit_names)}."
                    ]
                }
            )

    def validate(self, attrs):
        doc_date = attrs.get("doc_date") or getattr(self.instance, "doc_date", None)
        due_date = attrs.get("due_date")
        product = attrs.get("product") or getattr(self.instance, "product", None)
        document_types = attrs.get("document_types")
        doc_date_changed = (
            self.instance is not None
            and "doc_date" in attrs
            and attrs.get("doc_date") != getattr(self.instance, "doc_date", None)
        )

        if doc_date_changed:
            step_one_workflow = self._get_step_one_workflow(self.instance)
            if step_one_workflow and step_one_workflow.status == step_one_workflow.STATUS_COMPLETED:
                raise serializers.ValidationError(
                    {"doc_date": "Application submission date cannot be changed after step 1 is completed."}
                )

        if due_date is None:
            if doc_date_changed:
                due_date = self._calculate_due_date_for_doc_date(
                    doc_date=doc_date,
                    product=product,
                    application=self.instance,
                )
            else:
                due_date = getattr(self.instance, "due_date", None)

        if due_date and doc_date and due_date < doc_date:
            raise serializers.ValidationError({"due_date": "Due date cannot be before document date."})

        notify_customer_too = attrs.get("notify_customer_too")
        if notify_customer_too is None and self.instance is not None:
            notify_customer_too = self.instance.notify_customer_too
        notify_customer_channel = attrs.get("notify_customer_channel")
        if notify_customer_channel is None and self.instance is not None:
            notify_customer_channel = self.instance.notify_customer_channel

        customer = attrs.get("customer") or getattr(self.instance, "customer", None)

        if product and getattr(product, "deprecated", False):
            raise serializers.ValidationError({"product": "Deprecated products cannot be used for applications."})
        if product and not getattr(product, "uses_customer_app_workflow", False):
            raise serializers.ValidationError(
                {"product": "This product is invoice-only and does not support customer applications."}
            )

        self._validate_single_stay_permit_document_type(document_types)

        should_validate_submission_window = self.instance is None or "doc_date" in attrs or "product" in attrs
        if should_validate_submission_window:
            try:
                StayPermitSubmissionWindowService().validate_doc_date(
                    product=product,
                    doc_date=doc_date,
                    application=self.instance,
                )
            except DjangoValidationError as exc:
                if getattr(exc, "message_dict", None):
                    raise serializers.ValidationError(exc.message_dict)
                raise serializers.ValidationError({"doc_date": exc.messages})

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
        from customer_applications.services.stay_permit_workflow_schedule_service import (
            StayPermitWorkflowScheduleService,
        )
        from django.db import transaction
        from django.utils import timezone
        from products.models.document_type import DocumentType
        from products.models.task import Task

        document_types = validated_data.pop("document_types", [])
        user = self.context["request"].user

        # Create application
        if not validated_data.get("due_date"):
            validated_data["due_date"] = self._calculate_due_date_for_doc_date(
                doc_date=validated_data.get("doc_date"),
                product=validated_data.get("product"),
            )

        validated_data["created_by"] = user
        application = DocApplication.objects.create(**validated_data)

        # Pre-check if passport can be auto-imported to avoid creating placeholder
        has_auto_passport = self._can_auto_import_passport(application)

        # Resolve document types once to avoid per-item queries.
        normalized_doc_type_ids = []
        for dt in document_types:
            raw_id = dt.get("doc_type_id") or dt.get("id")
            try:
                normalized_id = int(raw_id)
            except (TypeError, ValueError):
                normalized_id = None
            normalized_doc_type_ids.append(normalized_id)
        document_types_by_id = DocumentType.objects.in_bulk(
            [doc_type_id for doc_type_id in normalized_doc_type_ids if doc_type_id]
        )

        # Create provided placeholder documents in one query.
        placeholder_documents = []
        now = timezone.now()
        for dt, doc_type_id in zip(document_types, normalized_doc_type_ids):
            required = dt.get("required", True)
            doc_type = document_types_by_id.get(doc_type_id)
            if not doc_type:
                raise serializers.ValidationError({"document_types": f"Invalid document type id: {doc_type_id}"})

            # Skip creating placeholder if passport will be auto-imported
            if doc_type.name == "Passport" and has_auto_passport:
                continue

            placeholder_documents.append(
                Document(
                    doc_application=application,
                    doc_type=doc_type,
                    required=required,
                    created_by=user,
                    created_at=now,
                    updated_at=now,
                )
            )

        if placeholder_documents:
            Document.objects.bulk_create(placeholder_documents)

        # Create the first workflow step immediately only when the application can already start.
        task = Task.objects.filter(product=application.product, step=1).first()
        if task:
            start_date = application.get_first_task_start_date()
            if start_date:
                step1 = DocWorkflow(
                    start_date=start_date,
                    task=task,
                    doc_application=application,
                    created_by=user,
                    status=DocWorkflow.STATUS_PENDING,
                )
                step1.due_date = application.calculate_next_calendar_due_date(start_date=start_date) or start_date
                step1.save()

        StayPermitWorkflowScheduleService().sync(application=application, actor_user_id=user.id)

        if has_auto_passport:
            from customer_applications.tasks import auto_import_passport_task

            transaction.on_commit(
                lambda: auto_import_passport_task(
                    application_id=application.id,
                    user_id=user.id,
                )
            )

        self._prime_detail_caches(application)

        return application

    def update(self, instance, validated_data):
        from customer_applications.models.doc_workflow import DocWorkflow
        from customer_applications.models.document import Document
        from customer_applications.services.stay_permit_workflow_schedule_service import (
            StayPermitWorkflowScheduleService,
        )
        from django.db import transaction
        from django.utils import timezone
        from products.models.document_type import DocumentType

        document_types = validated_data.pop("document_types", None)
        doc_date_changed = (
            "doc_date" in validated_data and validated_data.get("doc_date") != getattr(instance, "doc_date", None)
        )
        if doc_date_changed and "due_date" not in validated_data:
            validated_data["due_date"] = self._calculate_due_date_for_doc_date(
                doc_date=validated_data.get("doc_date"),
                product=validated_data.get("product") or getattr(instance, "product", None),
                application=instance,
            )

        step_one_workflow = self._get_step_one_workflow(instance) if doc_date_changed else None
        user = self.context.get("request").user if self.context.get("request") else None

        with transaction.atomic():
            application = super().update(instance, validated_data)

            if doc_date_changed and step_one_workflow:
                start_date = application.get_first_task_start_date()
                if start_date:
                    step_one_workflow.start_date = start_date
                    step_one_workflow.due_date = (
                        application.calculate_next_calendar_due_date(start_date=start_date) or start_date
                    )
                    step_one_workflow.updated_by = user
                    step_one_workflow.save()

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

            StayPermitWorkflowScheduleService().sync(
                application=application,
                actor_user_id=getattr(user, "id", None),
            )

            self._prime_detail_caches(application)

        return application

    def _prime_detail_caches(self, application) -> None:
        product = getattr(application, "product", None)
        if product is not None:
            product_prefetched = getattr(product, "_prefetched_objects_cache", None) or {}
            product_prefetched["tasks"] = list(product.tasks.all().order_by("step"))
            product._prefetched_objects_cache = product_prefetched

        documents = list(application.documents.select_related("doc_type", "created_by", "updated_by").all())
        workflows = list(application.workflows.select_related("task", "created_by", "updated_by").all())
        prefetched = getattr(application, "_prefetched_objects_cache", None) or {}
        prefetched.update(
            {
                "documents": documents,
                "workflows": workflows,
            }
        )
        application._prefetched_objects_cache = prefetched
        application.total_required_documents = sum(1 for document in documents if document.required)
        application.completed_required_documents = sum(
            1 for document in documents if document.required and document.completed
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
