from django.db import transaction
from django.utils import timezone

from core.utils.dateutils import calculate_due_date
from customer_applications.models import DocApplication
from customer_applications.models.doc_workflow import DocWorkflow
from customer_applications.models.document import Document
from customers.models import Customer
from products.models import Product
from products.models.document_type import DocumentType


def create_quick_customer(*, validated_data) -> Customer:
    return Customer.objects.create(**validated_data)


def create_quick_product(*, validated_data, user=None) -> Product:
    if validated_data.get("retail_price") is None:
        validated_data["retail_price"] = validated_data.get("base_price")
    if user:
        validated_data["created_by"] = user
        validated_data["updated_by"] = user
    return Product.objects.create(**validated_data)


def create_quick_customer_application(*, customer, product, doc_date, notes, created_by) -> DocApplication:
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
    due_date = calculate_due_date(
        start_date=doc_app.doc_date,
        days_to_complete=first_task.duration,
        business_days_only=first_task.duration_is_business_days,
    )
    DocWorkflow.objects.create(
        doc_application=doc_app,
        task=first_task,
        start_date=timezone.now().date(),
        due_date=due_date,
        status=DocWorkflow.STATUS_PENDING,
        created_by=created_by,
    )


def _split_document_names(value: str) -> list[str]:
    if not value:
        return []
    return [name.strip() for name in value.split(",") if name.strip()]
