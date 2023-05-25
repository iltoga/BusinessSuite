from django.db import models
from django.core.exceptions import ValidationError

class Product(models.Model):
    PRODUCT_TYPE_CHOICES = [
        ('visa', 'Visa'),
        ('other', 'Other'),
    ]

    name = models.CharField(max_length=100)
    code = models.CharField(max_length=20, unique=True)
    description = models.TextField(blank=True)
    base_price = models.DecimalField(max_digits=12, decimal_places=2, blank=True, null=True, default=0.00)
    product_type = models.CharField(max_length=50, choices=PRODUCT_TYPE_CHOICES, default='other')
    validity = models.PositiveIntegerField(blank=True, null=True)  # Validity in days
    required_documents = models.CharField(max_length=1024, blank=True)  # A comma-separated list of required documents

    class Meta:
        ordering = ['name']

    def __str__(self):
        return self.name


class Task(models.Model):
    product = models.ForeignKey(Product, related_name='tasks', on_delete=models.CASCADE)
    step = models.PositiveIntegerField()
    last_step = models.BooleanField(default=False)
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=0.00)
    duration = models.PositiveIntegerField()  # Duration in days
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

        other_tasks = Task.objects.filter(product=self.product, step=self.step)
        if self.pk:  # If this task is already in the database
            other_tasks = other_tasks.exclude(pk=self.pk)
        if other_tasks.exists():
            raise ValidationError("Each step within a product must be unique.")

