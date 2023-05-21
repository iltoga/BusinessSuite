from django.db import models
from .invoice import Invoice

class InvoiceItemRowManager(models.Manager):
    def calculate_amount(self):
        """Returns the amount calculated from unit_price and quantity."""
        return self.unit_price * self.quantity

    def calculate_due_amount(self):
        """Returns the due amount calculated from amount and paid_amount."""
        return self.amount - self.paid_amount

class InvoiceItemRow(models.Model):
    invoice = models.ForeignKey(Invoice, related_name='invoice_items', on_delete=models.CASCADE)
    id = models.AutoField(primary_key=True)
    item_code = models.CharField(max_length=50)
    description = models.TextField()
    quantity = models.IntegerField()
    unit_price = models.DecimalField(max_digits=12, decimal_places=2)
    amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    paid_amount = models.DecimalField(max_digits=12, decimal_places=2, default=0)
    due_amount = models.DecimalField(max_digits=12, decimal_places=2, editable=False)
    objects = InvoiceItemRowManager()  # Custom manager

    def save(self, *args, **kwargs):
        self.amount = InvoiceItemRow.objects.calculate_amount()
        self.paid_amount = max(self.paid_amount, 0)
        self.due_amount = InvoiceItemRow.objects.calculate_due_amount()
        super().save(*args, **kwargs)
