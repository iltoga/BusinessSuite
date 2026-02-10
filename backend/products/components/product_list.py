from django.db import models

from core.components.unicorn_search_list_view import UnicornSearchListView
from products.models import Product


class ProductListView(UnicornSearchListView):
    model = Product
    model_search_method = "search_products"
    items_per_page = 15

    def get_queryset(self):
        # Get the base queryset from the parent
        queryset = super().get_queryset()
        # Annotate with application count
        from customer_applications.models.doc_application import DocApplication

        return queryset.annotate(application_count=models.Count("doc_applications"))
