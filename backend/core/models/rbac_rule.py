from django.contrib.auth.models import Group
from django.db import models

ROLE_CHOICES = (
    ("is_staff", "Staff Status (is_staff)"),
    ("is_superuser", "Superuser Status (is_superuser)"),
)


class RbacMenuRule(models.Model):
    """Controls which groups can see which menus."""

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="menu_rules",
        help_text="If blank, applies to all authenticated users (unless overridden by role).",
    )
    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        blank=True,
        help_text="Optional: Apply this rule only to users with this specific Django role.",
    )
    menu_id = models.CharField(max_length=100, help_text="e.g., 'products', 'reports', 'admin'")
    is_visible = models.BooleanField(default=True)

    class Meta:
        unique_together = ("group", "role", "menu_id")
        verbose_name = "RBAC Menu Rule"
        verbose_name_plural = "RBAC Menu Rules"

    def __str__(self):
        target = "All Users"
        if self.group:
            target = f"Group: {self.group.name}"
        elif self.role:
            target = f"Role: {self.get_role_display()}"
        
        state = "Visible" if self.is_visible else "Hidden"
        return f"{target} - {self.menu_id}: {state}"


class RbacFieldRule(models.Model):
    """Controls which groups have read/write access to specific fields."""

    group = models.ForeignKey(
        Group,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="field_rules",
        help_text="If blank, applies to all authenticated users (unless overridden by role).",
    )
    role = models.CharField(
        max_length=50,
        choices=ROLE_CHOICES,
        blank=True,
        help_text="Optional: Apply this rule only to users with this specific Django role.",
    )
    model_name = models.CharField(max_length=100, help_text="e.g., 'product', 'customer'")
    field_name = models.CharField(max_length=100, help_text="e.g., 'base_price'")
    can_read = models.BooleanField(default=True)
    can_write = models.BooleanField(default=True)

    class Meta:
        unique_together = ("group", "role", "model_name", "field_name")
        verbose_name = "RBAC Field Rule"
        verbose_name_plural = "RBAC Field Rules"

    def __str__(self):
        target = "All Users"
        if self.group:
            target = f"Group: {self.group.name}"
        elif self.role:
            target = f"Role: {self.get_role_display()}"
            
        return f"{target} - {self.model_name}.{self.field_name}"
