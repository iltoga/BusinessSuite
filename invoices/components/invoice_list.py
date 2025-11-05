from django.db.models import DecimalField, F, Prefetch, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone
from django_unicorn.components import UnicornView

from core.components.unicorn_search_list_view import UnicornSearchListView
from invoices.models import Invoice
from invoices.models.invoice import InvoiceApplication


class InvoiceListView(UnicornSearchListView):
    model = Invoice
    model_search_method = "search_invoices"

    def mount(self):
        super().mount()
        self.today = timezone.now().date()

    def get_queryset(self):
        """Override to add optimized prefetching and annotations."""
        queryset = super().get_queryset()

        # Calculate total paid amount for the invoice
        paid_sum = Coalesce(Sum("invoice_applications__payments__amount"), Value(0, output_field=DecimalField()))

        # Optimize the queryset with select_related and prefetch_related
        queryset = (
            queryset.select_related("customer")
            .prefetch_related(
                Prefetch(
                    "invoice_applications",
                    queryset=(
                        InvoiceApplication.objects.select_related(
                            "customer_application__product", "customer_application__customer"
                        ).prefetch_related("payments")
                    ),
                    to_attr="prefetched_invoice_applications",
                )
            )
            .annotate(total_paid=paid_sum, total_due=F("total_amount") - paid_sum)
        )

        return queryset
