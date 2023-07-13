# models.py
from django.conf import settings
from django.contrib.postgres.search import SearchVector, TrigramSimilarity
from django.core import serializers
from django.db import models
from django.db.models import Q

from customer_applications.models.doc_application import DocApplication
from customers.models import Customer


class InvoiceQuerySet(models.QuerySet):
    """
    Custom queryset for Invoice model.
    """

    pass


class InvoiceManager(models.Manager):
    """
    Invoice Manager to enhance the default manager and
    add a search functionality.
    """

    def get_queryset(self):
        return InvoiceQuerySet(self.model, using=self._db)

    def search_invoices(self, query):
        """
        Search Invoices by customer, invoice number, invoice date, due date, status, invoice date year (this one exact match).
        Use the SearchVector to search across multiple fields.
        """
        return self.annotate(
            search=SearchVector(
                "invoice_no",
                "invoice_date",
                "due_date",
                "status",
                "invoice_date__year",
            ),
            first_name_similarity=TrigramSimilarity("customer__first_name", query),
            last_name_similarity=TrigramSimilarity("customer__last_name", query),
        ).filter(Q(search=query) | Q(first_name_similarity__gt=0.3) | Q(last_name_similarity__gt=0.3))

        # return self.filter(
        #     models.Q(customer__first_name__icontains=query)
        #     | models.Q(customer__last_name__icontains=query)
        #     | models.Q(invoice_no__icontains=query)
        #     | models.Q(invoice_date__icontains=query)
        #     | models.Q(due_date__icontains=query)
        #     | models.Q(status__icontains=query)
        #     | (models.Q(invoice_date__year=year_query) if year_query is not None else models.Q())
        # )


class Invoice(models.Model):
    CREATED = "created"
    PENDING_PAYMENT = "pending_payment"
    PARTIAL_PAYMENT = "partial_payment"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    PARTIALLY_REFUNDED = "partially_refunded"
    REFUNDED = "refunded"
    WRITE_OFF = "write_off"

    INVOICE_STATUS_CHOICES = [
        (CREATED, "Created"),
        (PENDING_PAYMENT, "Pending Payment"),
        (PARTIAL_PAYMENT, "Partial Payment"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
        (DISPUTED, "Disputed"),
        (CANCELLED, "Cancelled"),
        (PARTIALLY_REFUNDED, "Partially Refunded"),
        (REFUNDED, "Refunded"),
        (WRITE_OFF, "Write Off"),
    ]

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name="invoices")
    invoice_no = models.PositiveIntegerField(unique=True, db_index=True)
    invoice_date = models.DateField(db_index=True)
    due_date = models.DateField(db_index=True)
    sent = models.BooleanField(default=False)
    status = models.CharField(choices=INVOICE_STATUS_CHOICES, default=CREATED, max_length=20, db_index=True)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="created_by_invoice",
        null=True,
        blank=True,
    )
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="updated_by_invoice",
        null=True,
        blank=True,
    )
    objects = InvoiceManager()

    class Meta:
        ordering = ("-invoice_no",)

    @property
    def applications_json(self):
        applications = serializers.serialize("json", self.applications.all())
        return applications

    @property
    def invoice_no_display(self):
        # return f"{self.invoice_date.year}/{self.invoice_no:06d}"
        return f"{self.invoice_date.strftime('%Y-%m-%d')}/{self.invoice_no:08d}"

    def delete(self, *args, **kwargs):
        raise Exception("You can't delete an invoice.")

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            self.invoice_no = self.get_next_invoice_no()
        super().save(*args, **kwargs)

    def __str__(self):
        inv_no = f"{self.invoice_no_display}" if self.invoice_no else "New"
        customer = self.customer
        return f"{inv_no} - {customer}"

    # Custom methods

    def calculate_total_amount(self):
        tot = 0
        if self.invoice_applications and self.invoice_applications.exists():
            tot = self.invoice_applications.aggregate(models.Sum("amount"))["amount__sum"]
        return tot

    def get_next_invoice_no(self):
        last_invoice = Invoice.objects.last()
        if last_invoice:
            return last_invoice.invoice_no + 1
        return 1


class InvoiceApplication(models.Model):
    PENDING = "pending"
    PARTIAL_PAYMENT = "partial_payment"
    PAID = "paid"
    OVERDUE = "overdue"
    DISPUTED = "disputed"
    CANCELLED = "cancelled"
    REFUNDED = "refunded"
    WRITE_OFF = "write_off"

    PAYMENT_STATUS_CHOICES = [
        (PENDING, "Pending"),
        (PARTIAL_PAYMENT, "Partial Payment"),
        (PAID, "Paid"),
        (OVERDUE, "Overdue"),
        (DISPUTED, "Disputed"),
        (CANCELLED, "Cancelled"),
        (REFUNDED, "Refunded"),
        (WRITE_OFF, "Write Off"),
    ]

    invoice = models.ForeignKey(Invoice, related_name="invoice_applications", on_delete=models.CASCADE)
    customer_application = models.ForeignKey(
        DocApplication, related_name="invoice_applications", on_delete=models.CASCADE
    )
    due_amount = models.DecimalField(max_digits=10, decimal_places=2)
    paid_amount = models.DecimalField(default=0, max_digits=10, decimal_places=2)
    payment_status = models.CharField(choices=PAYMENT_STATUS_CHOICES, default=PENDING, max_length=20, db_index=True)

    class Meta:
        ordering = ("-id",)

    def __str__(self):
        return f"{self.invoice} - {self.customer_application}"


class Payment(models.Model):
    invoice_application = models.ForeignKey(InvoiceApplication, related_name="payments", on_delete=models.CASCADE)
    payment_date = models.DateField(auto_now_add=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    from_customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
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
