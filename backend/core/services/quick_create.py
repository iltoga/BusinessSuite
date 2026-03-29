"""
FILE_ROLE: Service-layer logic for the core app.

KEY_COMPONENTS:
- create_quick_customer: Module symbol.
- create_quick_product: Module symbol.
- create_quick_customer_application: Module symbol.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from customer_applications.models import DocApplication
from customer_applications.services.application_creation_service import CustomerApplicationCreationService
from customers.models import Customer
from products.models import Product


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

    Assumes serializer validation already applied product defaults and only
    stamps ``created_by`` / ``updated_by`` when *user* is provided.

    Args:
        validated_data: Pre-validated field dict ready for ``Product.objects.create()``.
        user: Optional request user; used to set audit fields.

    Returns:
        The newly created ``Product`` instance.
    """
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
    return CustomerApplicationCreationService().create(
        validated_data={
            "customer": customer,
            "product": product,
            "doc_date": doc_date,
            "notes": notes or "",
        },
        created_by=created_by,
        document_type_specs=None,
    )
