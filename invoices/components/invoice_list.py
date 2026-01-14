from django.db.models import DecimalField, F, OuterRef, Prefetch, Subquery, Sum, Value
from django.db.models.functions import Coalesce
from django.utils import timezone

from core.components.unicorn_search_list_view import UnicornSearchListView
from invoices.models import Invoice
from invoices.models.invoice import InvoiceApplication
from payments.models import Payment


class InvoiceListView(UnicornSearchListView):
    model = Invoice
    model_search_method = "search_invoices"
    hide_paid = False

    def mount(self):
        super().mount()
        self.today = timezone.now().date()

    def handle_hide_paid(self):
        # Trigger a refresh when the hide_paid checkbox changes state
        self.search()

    def get_queryset(self):
        """Override to add optimized prefetching and annotations."""
        queryset = super().get_queryset()

        # Use subquery to calculate total paid for the invoice
        payment_subquery = (
            Payment.objects.filter(invoice_application__invoice=OuterRef("pk"))
            .values("invoice_application__invoice")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        # Subquery for paid amount per InvoiceApplication
        app_payment_subquery = (
            Payment.objects.filter(invoice_application=OuterRef("pk"))
            .values("invoice_application")
            .annotate(total=Sum("amount"))
            .values("total")
        )

        # Optimize the queryset with select_related and prefetch_related
        queryset = (
            queryset.select_related("customer")
            .prefetch_related(
                Prefetch(
                    "invoice_applications",
                    queryset=InvoiceApplication.objects.select_related(
                        "customer_application__product", "customer_application__customer"
                    ).annotate(
                        annotated_paid_amount=Coalesce(
                            Subquery(app_payment_subquery), Value(0), output_field=DecimalField()
                        ),
                        annotated_due_amount=F("amount")
                        - Coalesce(Subquery(app_payment_subquery), Value(0), output_field=DecimalField()),
                    ),
                    to_attr="prefetched_invoice_applications",
                )
            )
            .annotate(
                total_paid_annotated=Coalesce(Subquery(payment_subquery), Value(0), output_field=DecimalField()),
            )
            .annotate(total_due_annotated=F("total_amount") - F("total_paid_annotated"))
        )

        return queryset

    def apply_filters(self, queryset):
        queryset = super().apply_filters(queryset)
        return self.apply_status_filters(queryset)

    def apply_status_filters(self, queryset):
        if self.hide_paid:
            queryset = queryset.exclude(status=Invoice.PAID)
        return queryset
