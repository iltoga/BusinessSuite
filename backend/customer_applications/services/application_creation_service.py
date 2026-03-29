"""
FILE_ROLE: Creates customer application records and their initial workflow/document scaffolding.

KEY_COMPONENTS:
- DocumentTypeSpec: Describes whether a document type is required for the new application.
- CustomerApplicationCreationService: Creates the application, placeholder documents, and initial workflow state.
- _calculate_due_date_for_doc_date: Calculates the initial due date from product/task rules.
- _document_type_specs_from_product: Builds document requirements from the product configuration.
- _prime_detail_caches: Prefetches related objects onto the created application instance.
- _can_auto_import_passport: Detects whether passport data can be reused for the new application.

INTERACTIONS:
- Depends on: customer_applications.models, customer_applications.services.stay_permit_submission_window_service, customer_applications.services.stay_permit_workflow_schedule_service, products.models.document_type, products.models.task
- Consumed by: application-creation flows that need a single domain path for new DocApplication records.

AI_GUIDELINES:
- Keep multi-model creation logic here and use transactions/callbacks for side effects already expected by the workflow.
- Do not push HTTP or serializer concerns into this service.
- Preserve the document/workflow bootstrapping order because downstream cache and task logic depends on it.
"""

from __future__ import annotations

from dataclasses import dataclass

from customer_applications.models import DocApplication
from django.core.files.storage import default_storage
from django.db import transaction
from django.utils import timezone
from products.models.document_type import DocumentType
from products.models.task import Task
from rest_framework import serializers


@dataclass(frozen=True)
class DocumentTypeSpec:
    doc_type_id: int
    required: bool


class CustomerApplicationCreationService:
    """Create customer applications through one shared domain path."""

    def create(
        self,
        *,
        validated_data: dict,
        created_by,
        document_type_specs: list[DocumentTypeSpec] | None = None,
    ) -> DocApplication:
        from customer_applications.models.doc_workflow import DocWorkflow
        from customer_applications.models.document import Document
        from customer_applications.services.stay_permit_submission_window_service import (
            StayPermitSubmissionWindowService,
        )
        from customer_applications.services.stay_permit_workflow_schedule_service import (
            StayPermitWorkflowScheduleService,
        )

        product = validated_data.get("product")
        doc_date = validated_data.get("doc_date")

        if product and getattr(product, "deprecated", False):
            raise serializers.ValidationError({"product": "Deprecated products cannot be used for applications."})
        if product and not getattr(product, "uses_customer_app_workflow", False):
            raise serializers.ValidationError(
                {"product": "This product is invoice-only and does not support customer applications."}
            )

        StayPermitSubmissionWindowService().validate_doc_date(
            product=product,
            doc_date=doc_date,
            application=None,
        )

        if not validated_data.get("due_date"):
            validated_data["due_date"] = self._calculate_due_date_for_doc_date(
                doc_date=doc_date,
                product=product,
            )

        payload = dict(validated_data)
        payload["created_by"] = created_by

        application = DocApplication.objects.create(**payload)
        has_auto_passport = self._can_auto_import_passport(application)
        document_type_specs = document_type_specs or self._document_type_specs_from_product(product)

        normalized_doc_type_ids = [item.doc_type_id for item in document_type_specs]
        document_types_by_id = DocumentType.objects.in_bulk(normalized_doc_type_ids)

        placeholder_documents = []
        now = timezone.now()
        for item in document_type_specs:
            doc_type = document_types_by_id.get(item.doc_type_id)
            if not doc_type:
                raise serializers.ValidationError({"document_types": f"Invalid document type id: {item.doc_type_id}"})

            if doc_type.name == "Passport" and has_auto_passport:
                continue

            placeholder_documents.append(
                Document(
                    doc_application=application,
                    doc_type=doc_type,
                    required=item.required,
                    created_by=created_by,
                    created_at=now,
                    updated_at=now,
                )
            )

        if placeholder_documents:
            Document.objects.bulk_create(placeholder_documents)

        task = Task.objects.filter(product=application.product, step=1).first()
        if task:
            start_date = application.get_first_task_start_date()
            if start_date:
                step1 = DocWorkflow(
                    start_date=start_date,
                    task=task,
                    doc_application=application,
                    created_by=created_by,
                    status=DocApplication.STATUS_PENDING,
                )
                step1.due_date = application.calculate_next_calendar_due_date(start_date=start_date) or start_date
                step1.save()

        StayPermitWorkflowScheduleService().sync(application=application, actor_user_id=created_by.id)

        if has_auto_passport:
            from customer_applications.tasks import auto_import_passport_task

            transaction.on_commit(
                lambda: auto_import_passport_task(
                    application_id=application.id,
                    user_id=created_by.id,
                )
            )

        self._prime_detail_caches(application)
        return application

    def _calculate_due_date_for_doc_date(self, *, doc_date, product=None):
        if not doc_date:
            return None

        from customer_applications.services.stay_permit_submission_window_service import (
            StayPermitSubmissionWindowService,
        )

        window_service = StayPermitSubmissionWindowService()
        if window_service.product_requires_submission_window(product):
            return None

        next_calendar_task = (
            product.tasks.filter(add_task_to_calendar=True).order_by("step").first() if product else None
        )
        if next_calendar_task:
            from core.utils.dateutils import calculate_due_date

            return calculate_due_date(
                doc_date,
                next_calendar_task.duration,
                next_calendar_task.duration_is_business_days,
            )

        return doc_date if product and product.tasks.exists() else None

    def _document_type_specs_from_product(self, product) -> list[DocumentTypeSpec]:
        if product is None:
            return []

        required_names = [name.strip() for name in (product.required_documents or "").split(",") if name.strip()]
        optional_names = [name.strip() for name in (product.optional_documents or "").split(",") if name.strip()]
        ordered_names = required_names + optional_names
        if not ordered_names:
            return []

        document_types_by_name = {
            doc_type.name: doc_type for doc_type in DocumentType.objects.filter(name__in=ordered_names)
        }

        specs: list[DocumentTypeSpec] = []
        for name in required_names:
            doc_type = document_types_by_name.get(name)
            if doc_type:
                specs.append(DocumentTypeSpec(doc_type_id=doc_type.id, required=True))
        for name in optional_names:
            doc_type = document_types_by_name.get(name)
            if doc_type:
                specs.append(DocumentTypeSpec(doc_type_id=doc_type.id, required=False))
        return specs

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
        from customer_applications.models.document import Document

        try:
            passport_doc_type = DocumentType.objects.get(name="Passport")
        except DocumentType.DoesNotExist:
            return False

        product = application.product
        all_docs = (product.required_documents or "") + "," + (product.optional_documents or "")
        doc_names = [item.strip() for item in all_docs.split(",") if item.strip()]
        if passport_doc_type.name not in doc_names:
            return False

        customer = application.customer
        if customer.passport_file and customer.passport_number and default_storage.exists(customer.passport_file.name):
            return True

        previous_doc = (
            Document.objects.filter(doc_application__customer=customer, doc_type=passport_doc_type)
            .exclude(doc_application=application)
            .order_by("-created_at")
            .first()
        )
        if previous_doc and previous_doc.file and not previous_doc.is_expired:
            return True

        return False
