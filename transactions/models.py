from django.db import models
from django.db.models.signals import pre_save
from django.dispatch import receiver
from customers.models import Customer
from invoices.models import InvoiceItemRow

class Transaction(models.Model):
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    invoice_item_row = models.ForeignKey(InvoiceItemRow, on_delete=models.CASCADE)
    item_code = models.CharField(max_length=50)
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    payment_date = models.DateTimeField(auto_now_add=True)
    completed = models.BooleanField(default=False)

    def check_completion(self):
        return self.amount >= self.invoice_item_row.due_amount

@receiver(pre_save, sender=Transaction)
def update_completed_status(sender, instance, **kwargs):
    instance.completed = instance.check_completion()
