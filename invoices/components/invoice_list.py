from django_unicorn.components import UnicornView

from core.components.unicorn_search_list_view import UnicornSearchListView
from invoices.models import Invoice


class InvoiceListView(UnicornView):
    pass


class InvoiceListView(UnicornSearchListView):
    model = Invoice
    model_search_method = "search_invoices"
