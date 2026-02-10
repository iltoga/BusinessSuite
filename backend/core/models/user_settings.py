"""User settings model and signals.

Provides a OneToOne `UserSettings` model that is auto-created when a
`User` is created using post_save signals. Uses a JSONField for
`preferences` with backwards compatibility for Django versions prior to
3.1 (which introduced `models.JSONField`).
"""
from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver

# JSONField compatibility: Django 3.1+ provides models.JSONField; older
# versions rely on contrib.postgres.fields.JSONField
try:
    from django.db.models import JSONField  # type: ignore
except Exception:  # pragma: no cover - fallback for older Django
    from django.contrib.postgres.fields import JSONField  # type: ignore


class UserSettings(models.Model):
    """Per-user settings stored as simple fields and a JSON preferences blob."""

    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="settings")
    theme = models.CharField(max_length=50, default="starlight")
    dark_mode = models.BooleanField(default=False)
    preferences = JSONField(default=dict, blank=True)

    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "User Settings"
        verbose_name_plural = "User Settings"

    def __str__(self):
        # Use username for readability; fallback to PK if username not present
        username = getattr(self.user, "username", None)
        return f"Settings for {username or self.user.pk}"


# Signals to ensure UserSettings exists for every User
@receiver(post_save, sender=User)
def create_user_settings(sender, instance, created, **kwargs):
    if created:
        UserSettings.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_settings(sender, instance, **kwargs):
    # Ensure settings exist and save them when the User is saved.
    if not hasattr(instance, "settings"):
        UserSettings.objects.create(user=instance)
    instance.settings.save()
