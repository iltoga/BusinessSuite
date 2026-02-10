import os

from django.contrib.auth.models import User
from django.db import models
from django.db.models.signals import post_save
from django.dispatch import receiver


def get_avatar_upload_to(instance, filename):
    """
    Returns the upload_to path for the avatar image.
    """
    ext = os.path.splitext(filename)[1]
    return f"avatars/user_{instance.user.id}{ext}"


class UserProfile(models.Model):
    user = models.OneToOneField(User, on_delete=models.CASCADE, related_name="profile")
    avatar = models.ImageField(upload_to=get_avatar_upload_to, null=True, blank=True)

    def __str__(self):
        return f"Profile for {self.user.username}"


# Signals to ensure UserProfile exists for every User
@receiver(post_save, sender=User)
def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.get_or_create(user=instance)


@receiver(post_save, sender=User)
def save_user_profile(sender, instance, **kwargs):
    if not hasattr(instance, "profile"):
        UserProfile.objects.create(user=instance)
    instance.profile.save()
