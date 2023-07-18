from django.conf import settings
from django.contrib.postgres.search import SearchVector, TrigramSimilarity
from django.db import models
from django.db.models import Q
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from django.utils import timezone

from customers.models import Customer
from invoices.models.invoice import InvoiceApplication


class PaymentQuerySet(models.QuerySet):
    """
    Custom queryset for Payment model.
    """

    pass


class PaymentManager(models.Manager):
    """
    Payment Manager to enhance the default manager and
    add a search functionality.
    """

    def get_queryset(self):
        return PaymentQuerySet(self.model, using=self._db)

    def search_payments(self, query):
        """
        Search Payments by customer, invoice number, invoice date, due date, status, invoice date year (this one exact match).
        Use the SearchVector to search across multiple fields.
        """
        return self.annotate(
            search=SearchVector(
                "payment_date",
                "invoice_application__invoice__invoice_no",
            ),
            first_name_similarity=TrigramSimilarity("from_customer__first_name", query),
            last_name_similarity=TrigramSimilarity("from_customer__last_name", query),
        ).filter(Q(search=query) | Q(first_name_similarity__gt=0.3) | Q(last_name_similarity__gt=0.3))

        # return self.filter(
        #     models.Q(from_customer__first_name__icontains=query)
        #     | models.Q(from_customer__last_name__icontains=query)
        #     | models.Q(invoice_application__invoice_no__icontains=query)
        #     | models.Q(payment_date__icontains=query)
        # )


class Payment(models.Model):
    invoice_application = models.ForeignKey(InvoiceApplication, related_name="payments", on_delete=models.CASCADE)
    from_customer = models.ForeignKey(Customer, related_name="payments", on_delete=models.CASCADE)
    payment_date = models.DateField(db_index=True, default=timezone.now)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    notes = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_by_payment",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_by_payment",
        null=True,
        blank=True,
    )
    objects = PaymentManager()


# after delete update the invoice application to update the status and invoice to update totals
@receiver(post_delete, sender=Payment)
@receiver(post_save, sender=Payment)
def update_invoice_status(sender, instance, **kwargs):
    instance.invoice_application.save()
    instance.invoice_application.invoice.save()
