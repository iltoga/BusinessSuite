# models.py
from django.conf import settings
from django.core import serializers
from django.db import models

from customer_applications.models.doc_application import DocApplication
from customers.models import Customer


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

    class Meta:
        ordering = ("-invoice_no",)

    @property
    def applications_json(self):
        applications = serializers.serialize("json", self.applications.all())
        return applications

    @property
    def tot_paid_amount(self):
        return sum(application.paid_amount for application in self.invoiceapplication_set.all())

    @property
    def tot_due_amount(self):
        return self.total_amount - self.tot_paid_amount

    def delete(self, *args, **kwargs):
        raise Exception("You can't delete an invoice.")

    def save(self, *args, **kwargs):
        if not self.invoice_no:
            self.invoice_no = self.get_next_invoice_no()
            self.total_amount = self.calculate_total_amount()
        super().save(*args, **kwargs)

    def __str__(self):
        inv_no = f"Inv no. {self.invoice_no} -" if self.invoice_no else "New -"
        inv_year = f"- {self.invoice_date.year}" if self.invoice_date else ""
        return f"{inv_no} {self.customer} {self.invoice_date}"

    # Custom methods

    def calculate_total_amount(self):
        if self.pk is None:
            # The instance has not been saved to the database yet, return a default value
            return 0
        else:
            tot = 0
            if self.invoice_applications.exists():
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


class Payment(models.Model):
    invoice_application = models.ForeignKey(InvoiceApplication, related_name="payments", on_delete=models.CASCADE)
    payment_date = models.DateField(auto_now_add=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2)
    from_customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)
