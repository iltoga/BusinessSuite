"""
core.services.quick_create
==========================
Convenience factory functions used by the "quick-create" API endpoints to
create domain objects with sensible defaults from a minimal payload.

Creation chain for ``create_quick_customer_application()``
----------------------------------------------------------
1. Validate that the chosen product uses the customer-application workflow
   (``product.uses_customer_app_workflow``).  Invoice-only products raise a
   ``ValidationError`` immediately.
2. Validate the document date against the product's submission window via
   ``StayPermitSubmissionWindowService``.
3. Inside ``transaction.atomic()``:
   a. Create the ``DocApplication`` record.
   b. Create ``Document`` rows for every required and optional document type
      listed on the product (``required_documents`` / ``optional_documents``
      name-lists).
   c. Create the first ``DocWorkflow`` step, computing its ``due_date`` from
      the task's ``duration`` / ``duration_is_business_days`` settings via
      ``calculate_due_date()``.

Side effects
------------
- ``Document.completed`` is auto-calculated in ``Document.save()`` based on
  ``DocumentType.requires_verification`` — no explicit flag is set here.
- The first ``DocWorkflow`` step is created in ``STATUS_PENDING``; subsequent
  steps are created by the workflow progression service when each step is
  completed.
"""

from core.utils.dateutils import calculate_due_date
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow
from customer_applications.models.document import Document
from customer_applications.services.stay_permit_submission_window_service import StayPermitSubmissionWindowService
from customers.models import Customer
from django.db import transaction
from products.models import Product, ProductCategory
from products.models.document_type import DocumentType


def create_quick_customer(*, validated_data) -> Customer:
    """Create a ``Customer`` from a pre-validated data dict.

    Args:
        validated_data: Keyword arguments forwarded directly to
            ``Customer.objects.create()``.  Must satisfy all model constraints.

    Returns:
        The newly created ``Customer`` instance.
    """
    return Customer.objects.create(**validated_data)


def create_quick_product(*, validated_data, user=None) -> Product:
    """Create a ``Product`` with automatic defaults for optional fields.

    Fills in ``product_category`` from ``ProductCategory.get_default_for_type()``
    when absent, mirrors ``base_price`` → ``retail_price`` when retail price is
    omitted, and stamps ``created_by`` / ``updated_by`` when *user* is provided.

    Args:
        validated_data: Pre-validated field dict.  ``product_type`` is consumed
            (popped) when ``product_category`` is absent.
        user: Optional request user; used to set audit fields.

    Returns:
        The newly created ``Product`` instance.
    """
    if not validated_data.get("product_category"):
        product_type = validated_data.pop("product_type", None)
        validated_data["product_category"] = ProductCategory.get_default_for_type(product_type)
    if validated_data.get("retail_price") is None:
        validated_data["retail_price"] = validated_data.get("base_price")
    if user:
        validated_data["created_by"] = user
        validated_data["updated_by"] = user
    return Product.objects.create(**validated_data)


def create_quick_customer_application(*, customer, product, doc_date, notes, created_by) -> DocApplication:
    """Create a ``DocApplication`` together with its initial documents and first workflow step.

    This is the canonical entry point for the quick-create flow.  See module
    docstring for the full creation chain and side-effect details.

    Args:
        customer: ``Customer`` instance to link the application to.
        product: ``Product`` instance; must have
            ``uses_customer_app_workflow=True``.
        doc_date: Application document date (start of submission window).
        notes: Optional free-text notes to attach.
        created_by: Request user; stored on the application and all child records.

    Returns:
        The newly created ``DocApplication`` instance (with related documents
        and first workflow step already committed).

    Raises:
        rest_framework.exceptions.ValidationError: When the product is
            invoice-only or ``doc_date`` falls outside the product's submission
            window.
    """
    if not getattr(product, "uses_customer_app_workflow", False):
        from rest_framework.exceptions import ValidationError

        raise ValidationError("Selected product is invoice-only and cannot create a customer application.")

    StayPermitSubmissionWindowService().validate_doc_date(
        product=product,
        doc_date=doc_date,
        application=None,
    )

    with transaction.atomic():
        doc_app = DocApplication.objects.create(
            customer=customer,
            product=product,
            doc_date=doc_date,
            notes=notes or "",
            created_by=created_by,
        )
        _create_documents_for_product(doc_app=doc_app, product=product, created_by=created_by)
        _create_initial_workflow(doc_app=doc_app, product=product, created_by=created_by)
    return doc_app


def _create_documents_for_product(*, doc_app, product, created_by) -> None:
    required_doc_names = _split_document_names(product.required_documents)
    optional_doc_names = _split_document_names(product.optional_documents)

    document_names = list(dict.fromkeys(required_doc_names + optional_doc_names))
    doc_types = DocumentType.objects.filter(name__in=document_names)
    doc_type_map = {doc_type.name: doc_type for doc_type in doc_types}

    for doc_name in required_doc_names:
        doc_type = doc_type_map.get(doc_name)
        if doc_type:
            Document.objects.create(
                doc_application=doc_app,
                doc_type=doc_type,
                required=True,
                created_by=created_by,
            )

    for doc_name in optional_doc_names:
        doc_type = doc_type_map.get(doc_name)
        if doc_type:
            Document.objects.create(
                doc_application=doc_app,
                doc_type=doc_type,
                required=False,
                created_by=created_by,
            )


def _create_initial_workflow(*, doc_app, product, created_by) -> None:
    first_task = product.tasks.order_by("step").first()
    if not first_task:
        return
    start_date = doc_app.get_first_task_start_date()
    if not start_date:
        return
    due_date = calculate_due_date(
        start_date=start_date,
        days_to_complete=first_task.duration,
        business_days_only=first_task.duration_is_business_days,
    )
    DocWorkflow.objects.create(
        doc_application=doc_app,
        task=first_task,
        start_date=start_date,
        due_date=due_date,
        status=DocApplication.STATUS_PENDING,
        created_by=created_by,
    )


def _split_document_names(value: str) -> list[str]:
    if not value:
        return []
    return [name.strip() for name in value.split(",") if name.strip()]
