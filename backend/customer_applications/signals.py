from django.db.models.signals import post_delete, post_save
from django.dispatch import receiver

from customer_applications.models import WorkflowNotification
from customer_applications.services.workflow_notification_stream import (
    bump_workflow_notification_stream_cursor,
    is_recent_workflow_notification,
)


@receiver(post_save, sender=WorkflowNotification, dispatch_uid="workflow_notification_stream_post_save")
def workflow_notification_post_save(sender, instance, created, **kwargs):
    if not is_recent_workflow_notification(instance):
        return
    bump_workflow_notification_stream_cursor(
        notification_id=instance.id,
        operation="created" if created else "updated",
    )


@receiver(post_delete, sender=WorkflowNotification, dispatch_uid="workflow_notification_stream_post_delete")
def workflow_notification_post_delete(sender, instance, **kwargs):
    if not is_recent_workflow_notification(instance):
        return
    bump_workflow_notification_stream_cursor(notification_id=instance.id, operation="deleted")

