"""Django signal handlers for document type hooks.

This module connects Django signals to the hook registry, dispatching
lifecycle events to registered hooks based on document type.
"""

from django.db.models.signals import post_init, post_save, pre_delete, pre_save
from django.dispatch import receiver

from customer_applications.models import Document

from .registry import hook_registry


@receiver(post_init, sender=Document)
def document_post_init(sender, instance, **kwargs):
    """Dispatch on_init to the registered hook when a Document is initialized."""
    if instance.doc_type_id:
        hook = hook_registry.get_hook(instance.doc_type.name)
        if hook:
            hook.on_init(instance)


@receiver(pre_save, sender=Document)
def document_pre_save(sender, instance, **kwargs):
    """Dispatch on_pre_save to the registered hook before a Document is saved."""
    if instance.doc_type_id:
        created = instance.pk is None
        hook = hook_registry.get_hook(instance.doc_type.name)
        if hook:
            hook.on_pre_save(instance, created)


@receiver(post_save, sender=Document)
def document_post_save(sender, instance, created, **kwargs):
    """Dispatch on_post_save to the registered hook after a Document is saved."""
    if instance.doc_type_id:
        hook = hook_registry.get_hook(instance.doc_type.name)
        if hook:
            hook.on_post_save(instance, created)


@receiver(pre_delete, sender=Document)
def document_pre_delete(sender, instance, **kwargs):
    """Dispatch on_pre_delete to the registered hook before a Document is deleted."""
    if instance.doc_type_id:
        hook = hook_registry.get_hook(instance.doc_type.name)
        if hook:
            hook.on_pre_delete(instance)
