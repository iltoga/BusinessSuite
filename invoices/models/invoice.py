# models.py
from decimal import Decimal

from django.core.validators import MinValueValidator
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

    STATUS_CHOICES = [
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

    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    invoice_no = models.PositiveIntegerField(unique=True, db_index=True)
    invoice_date = models.DateField(auto_now_add=True, db_index=True)
    due_date = models.DateField(db_index=True)
    sent = models.BooleanField(default=False)
    status = models.CharField(choices=STATUS_CHOICES, default=CREATED, max_length=20, db_index=True)
    notes = models.TextField(blank=True)
    total_amount = models.DecimalField(max_digits=12, decimal_places=2)

    class Meta:
        ordering = ("-invoice_no",)

    @property
    def tot_paid_amount(self):
        return sum(application.paid_amount for application in self.invoiceapplication_set.all())

    @property
    def tot_due_amount(self):
        return self.total_amount - self.tot_paid_amount


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

    invoice = models.ForeignKey(Invoice, on_delete=models.CASCADE)
    customer_application = models.ForeignKey(DocApplication, on_delete=models.CASCADE)
    due_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    paid_amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    payment_status = models.CharField(choices=PAYMENT_STATUS_CHOICES, default=PENDING, max_length=20, db_index=True)


class Payment(models.Model):
    invoice_application = models.ForeignKey(InvoiceApplication, on_delete=models.CASCADE)
    payment_date = models.DateField(auto_now_add=True, db_index=True)
    amount = models.DecimalField(max_digits=10, decimal_places=2, validators=[MinValueValidator(Decimal("0.01"))])
    from_customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    notes = models.TextField(blank=True)
