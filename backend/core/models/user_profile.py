"""
FILE_ROLE: Primary data models for the core app.

KEY_COMPONENTS:
- get_avatar_upload_to: Module symbol.
- UserProfile: Module symbol.
- create_user_profile: Module symbol.
- save_user_profile: Module symbol.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

import os
from logging import getLogger

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.db.utils import DatabaseError, IntegrityError
from django.dispatch import receiver

logger = getLogger(__name__)


def get_avatar_upload_to(instance, filename):
    """
    Returns the upload_to path for the avatar image.
    """
    ext = os.path.splitext(filename)[1]
    return f"avatars/user_{instance.user.id}{ext}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to=get_avatar_upload_to, null=True, blank=True)
    cache_enabled = models.BooleanField(
        default=True,
        db_index=True,
        help_text="Whether caching is enabled for this user. When disabled, all cache operations are bypassed.",
    )

    def __str__(self):
        return f"Profile for {self.user.username}"


# Signals to ensure UserProfile exists for every User
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    # Avoid resolving the reverse one-to-one relation on every user save (e.g. login
    # last_login updates). This keeps auth flow resilient when profile schema lags behind.
    if UserProfile.objects.filter(user_id=instance.pk).exists():
        return

    try:
        UserProfile.objects.create(user=instance)
    except IntegrityError:
        # Expected race: profile created between exists() check and create().
        logger.debug("UserProfile already exists for user_id=%s (race condition)", instance.pk)
    except DatabaseError:
        logger.exception("Unable to auto-create UserProfile for user_id=%s", instance.pk)
