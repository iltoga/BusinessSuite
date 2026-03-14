from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import models
from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver
from products.models.product import Product


class Task(models.Model):
    product = models.ForeignKey(Product, related_name="tasks", on_delete=models.CASCADE)
    step = models.PositiveIntegerField(db_index=True)
    last_step = models.BooleanField(default=False, db_index=True)
    name = models.CharField(max_length=100, db_index=True)
    description = models.TextField(blank=True, null=True)
    cost = models.DecimalField(max_digits=12, decimal_places=2, default=Decimal("0.00"))
    # Duration in days and a boolean to indicate if the duration is in business days
    duration = models.PositiveIntegerField(db_index=True, default=0)
    duration_is_business_days = models.BooleanField(default=True)
    # Notify the user this many days before the task is due
    notify_days_before = models.PositiveIntegerField(blank=True, default=0)
    add_task_to_calendar = models.BooleanField(default=False, db_index=True)
    notify_customer = models.BooleanField(default=False, db_index=True)

    class Meta:
        ordering = ["step"]
        unique_together = (("product", "step"),)

    def __str__(self):
        return self.name

    def clean(self):
        if self.notify_days_before and self.notify_days_before > self.duration:
            raise ValidationError("notify_days_before cannot be greater than duration.")

        if self.notify_customer and not self.add_task_to_calendar:
            raise ValidationError("notify_customer requires add_task_to_calendar to be enabled.")

        if self.cost and self.cost < 0:
            raise ValidationError("cost cannot be negative.")

        other_tasks = (
            Task.objects.filter(product=self.product, step=self.step).exclude(pk=self.pk).select_related("product")
        )
        if other_tasks.exists():
            raise ValidationError("Each step within a product must be unique.")

        # there cannot be two last steps in a product
        if self.last_step:
            other_last_steps = (
                Task.objects.filter(product=self.product, last_step=True).exclude(pk=self.pk).select_related("product")
            )
            if other_last_steps.exists():
                # add error to the field
                raise ValidationError(
                    f"Each product can only have one last step. The other last step is {other_last_steps[0].step}."
                )


def _sync_product_workflow_flag(product_id: int | None) -> None:
    if not product_id:
        return
    product = Product.objects.filter(id=product_id).first()
    if not product:
        return
    desired = product.recompute_uses_customer_app_workflow()
    if product.uses_customer_app_workflow != desired:
        product.uses_customer_app_workflow = desired
        product.save(update_fields=["uses_customer_app_workflow", "updated_at"])


@receiver(post_save, sender=Task)
def task_post_save_sync_product_workflow_flag(sender, instance, **kwargs):
    _sync_product_workflow_flag(instance.product_id)


@receiver(post_delete, sender=Task)
def task_post_delete_sync_product_workflow_flag(sender, instance, **kwargs):
    _sync_product_workflow_flag(instance.product_id)
