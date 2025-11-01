from django.utils import timezone
from django_unicorn.components import UnicornView

from core.components.unicorn_search_list_view import UnicornSearchListView
from invoices.models import Invoice


class InvoiceListView(UnicornSearchListView):
    model = Invoice
    model_search_method = "search_invoices"

    def mount(self):
        super().mount()
        self.today = timezone.now().date()
