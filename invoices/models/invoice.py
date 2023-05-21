from django.db import models

from django.core.exceptions import ValidationError

class InvoiceManager(models.Manager):
    def next_invoice_no(self):
        """Returns the next invoice number."""
        return self.aggregate(models.Max('invoice_no'))['invoice_no__max'] or 0 + 1

    def is_invoice_no_exist(self, invoice_no):
        return self.filter(invoice_no=invoice_no).exists()

class Invoice(models.Model):
    invoice_no = models.IntegerField(primary_key=True)
    date = models.DateTimeField()
    customer = models.ForeignKey('customers.Customer', on_delete=models.CASCADE)
    objects = InvoiceManager()  # Custom manager

    @property
    def total_amount(self):
        return sum(item.amount for item in self.invoice_items.all())

    @property
    def paid_amount(self):
        return sum(item.paid_amount for item in self.invoice_items.all())

    @property
    def due_amount(self):
        return self.total_amount - self.paid_amount

    def save(self, *args, **kwargs):
        if self._state.adding:  # This checks if object is being created and not updated
            # if invoice_no already exists, raise an error
            if Invoice.objects.is_invoice_no_exist(self.invoice_no):
                raise ValidationError('Invoice number already exists.')
        super().save(*args, **kwargs)
