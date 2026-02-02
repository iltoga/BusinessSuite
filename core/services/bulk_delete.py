from django.db import transaction
from django.db.models import Q

from customer_applications.models import DocApplication
from customers.models import Customer
from products.models import Product


def bulk_delete_customers(query: str | None = None, hide_disabled: bool = True) -> int:
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
    queryset = Product.objects.all()
    if query:
        queryset = queryset.filter(
            Q(name__icontains=query) | Q(code__icontains=query) | Q(product_type__icontains=query)
        )

    with transaction.atomic():
        count = queryset.count()
        queryset.delete()

    return count


def bulk_delete_applications(query: str | None = None) -> int:
    queryset = DocApplication.objects.all()
    if query:
        queryset = DocApplication.objects.search_doc_applications(query)

    with transaction.atomic():
        count = queryset.count()
        queryset.delete()

    return count
