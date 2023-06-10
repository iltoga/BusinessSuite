from django.db import models
from django.core.exceptions import ValidationError
from products.models.product import Product

class Task(models.Model):
    product = models.ForeignKey(Product, related_name='tasks', on_delete=models.CASCADE)
    step = models.PositiveIntegerField(db_index=True)
    last_step = models.BooleanField(default=False, db_index=True)
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, null=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    # Duration in days and a boolean to indicate if the duration is in business days
    duration = models.PositiveIntegerField(db_index=True)
    duration_is_business_days = models.BooleanField(default=True)

    notify_days_before = models.PositiveIntegerField(blank=True, null=True)  # Notify the user this many days before the task is due

    class Meta:
        ordering = ['step']
        unique_together = (('product', 'step'),)

    def __str__(self):
        return self.name

    def clean(self):
        if self.notify_days_before and self.notify_days_before > self.duration:
            raise ValidationError("notify_days_before cannot be greater than duration.")

        if self.cost and self.cost < 0:
            raise ValidationError("cost cannot be negative.")

        other_tasks = Task.objects.filter(product=self.product, step=self.step).exclude(pk=self.pk).select_related('product')
        if other_tasks.exists():
            raise ValidationError("Each step within a product must be unique.")

        # there cannot be two last steps in a product
        if self.last_step:
            other_last_steps = Task.objects.filter(product=self.product, last_step=True).exclude(pk=self.pk).select_related('product')
            if other_last_steps.exists():
                # add error to the field
                raise ValidationError(f"Each product can only have one last step. The other last step is {other_last_steps[0].step}.")
