"""
core.services.bulk_delete
=========================
Service functions for bulk deletion of top-level domain objects (customers,
products, customer applications).  Each function accepts optional filter
arguments, builds the corresponding QuerySet via the model's custom search
manager, and deletes all matching rows inside a single ``transaction.atomic()``
block so the count returned is always consistent with what was actually removed.

Note: ``QuerySet.delete()`` bypasses individual ``Model.delete()`` hooks.  These
functions are therefore only safe to call when no signal-based side-effects (e.g.
cascade cleanup in Python) are required.  Foreign-key cascade is handled at the
database level via ``ON DELETE CASCADE``.
"""

from customer_applications.models import DocApplication
from customers.models import Customer
from django.db import transaction
from django.db.models import Q
from products.models import Product


def bulk_delete_customers(query: str | None = None, hide_disabled: bool = True) -> int:
    """Delete customers matching *query*, optionally limiting to active records.

    Args:
        query: Free-text search string forwarded to
            ``Customer.objects.search_customers()``.  When ``None`` all
            customers (subject to *hide_disabled*) are targeted.
        hide_disabled: When ``True`` (default) only ``active=True`` customers
            are included in the deletion set.

    Returns:
        Number of ``Customer`` rows deleted.

    Raises:
        django.db.DatabaseError: If the database transaction fails.
    """
    queryset = Customer.objects.all()
    if query:
        queryset = Customer.objects.search_customers(query)
    if hide_disabled:
        queryset = queryset.filter(active=True)

    with transaction.atomic():
        count = queryset.count()
        queryset.delete()

    return count


def bulk_delete_products(query: str | None = None) -> int:
    """Delete products matching *query*.

    Args:
        query: Free-text search string forwarded to
            ``Product.objects.search_products()``.  When ``None`` all products
            are targeted.

    Returns:
        Number of ``Product`` rows deleted.
    """
    queryset = Product.objects.all()
    if query:
        queryset = Product.objects.search_products(query)

    with transaction.atomic():
        count = queryset.count()
        queryset.delete()

    return count


def bulk_delete_applications(query: str | None = None) -> int:
    """Delete customer applications matching *query*.

    Args:
        query: Free-text search string forwarded to
            ``DocApplication.objects.search_doc_applications()``.  When
            ``None`` all applications are targeted.

    Returns:
        Number of ``DocApplication`` rows deleted.

    Note:
        This will also cascade-delete related ``Document`` and ``DocWorkflow``
        rows at the database level.  Verify ``ON DELETE CASCADE`` constraints
        before calling in production.
    """
    queryset = DocApplication.objects.all()
    if query:
        queryset = DocApplication.objects.search_doc_applications(query)

    with transaction.atomic():
        count = queryset.count()
        queryset.delete()

    return count
