from __future__ import annotations

from django.apps import apps
from django.db.models.signals import post_delete, post_save

from core.services.sync_service import capture_model_delete, capture_model_upsert, is_sync_apply_in_progress


TRACKED_MODELS: list[tuple[str, str]] = [
    ("core", "LocalResilienceSettings"),
    ("customers", "Customer"),
    ("customer_applications", "DocApplication"),
    ("customer_applications", "Document"),
    ("customer_applications", "DocWorkflow"),
    ("customer_applications", "WorkflowNotification"),
    ("invoices", "Invoice"),
    ("invoices", "InvoiceApplication"),
    ("payments", "Payment"),
    ("products", "Product"),
    ("products", "Task"),
    ("core", "CalendarReminder"),
    ("core", "CalendarEvent"),
    ("core", "Holiday"),
    ("core", "CountryCode"),
]


def _on_tracked_save(sender, instance, **kwargs):
    if is_sync_apply_in_progress():
        return
    if getattr(instance, "_sync_skip_capture", False):
        return
    capture_model_upsert(instance)


def _on_tracked_delete(sender, instance, **kwargs):
    if is_sync_apply_in_progress():
        return
    capture_model_delete(sender._meta.label_lower, instance.pk)


def register_sync_signals() -> None:
    for app_label, model_name in TRACKED_MODELS:
        try:
            model = apps.get_model(app_label, model_name)
        except LookupError:
            continue

        dispatch_save_uid = f"sync_capture_save_{model._meta.label_lower}"
        dispatch_delete_uid = f"sync_capture_delete_{model._meta.label_lower}"
        post_save.connect(_on_tracked_save, sender=model, weak=False, dispatch_uid=dispatch_save_uid)
        post_delete.connect(_on_tracked_delete, sender=model, weak=False, dispatch_uid=dispatch_delete_uid)


register_sync_signals()
