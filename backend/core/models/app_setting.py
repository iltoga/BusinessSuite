"""
FILE_ROLE: Primary data models for the core app.

KEY_COMPONENTS:
- AppSetting: Module symbol.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on model definitions and local invariants.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

from django.conf import settings
from django.db import models


class AppSetting(models.Model):
    SCOPE_BACKEND = "backend"
    SCOPE_FRONTEND = "frontend"
    SCOPE_BOTH = "both"
    SCOPE_CHOICES = (
        (SCOPE_BACKEND, "Backend"),
        (SCOPE_FRONTEND, "Frontend"),
        (SCOPE_BOTH, "Frontend + Backend"),
    )

    name = models.CharField(max_length=120, unique=True, db_index=True)
    value = models.TextField(default="", blank=True)
    scope = models.CharField(max_length=16, choices=SCOPE_CHOICES, default=SCOPE_BACKEND)
    description = models.TextField(default="", blank=True)
    is_runtime_override = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="updated_app_settings",
    )

    class Meta:
        verbose_name = "Application Setting"
        verbose_name_plural = "Application Settings"
        ordering = ("name",)

    def __str__(self) -> str:
        return f"{self.name} ({self.scope})"
