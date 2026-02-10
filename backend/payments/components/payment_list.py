from core.components.unicorn_search_list_view import UnicornSearchListView
from payments.models import Payment


class PaymentListView(UnicornSearchListView):
    model = Payment
    model_search_method = "search_payments"

    def get_queryset(self):
        """Override to add optimized select_related to reduce N+1 queries."""
        queryset = super().get_queryset()

        # Optimize with select_related for foreign key relationships used in the template
        queryset = queryset.select_related(
            "invoice_application__invoice",
            "invoice_application__customer_application__product",
            "invoice_application__customer_application__customer",
            "from_customer",
        )

        return queryset
