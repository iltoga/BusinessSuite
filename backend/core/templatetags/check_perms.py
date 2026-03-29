"""
FILE_ROLE: Provides template filters for permission checks in Django templates.

KEY_COMPONENTS:
- has_any_perm: Checks whether a user has any permission for a model.
- has_perm: Checks a specific app/model permission prefix in templates.

INTERACTIONS:
- Depends on: django.template, Django auth permissions on the user object.

AI_GUIDELINES:
- Keep filters side-effect free and safe for template rendering.
- Do not add business logic here; this file should stay limited to presentation-time permission checks.
"""

from django import template

register = template.Library()


@register.filter
def has_any_perm(user, model):
    if user.is_superuser:
        return True
    user_permissions = user.user_permissions.filter(content_type__model=model).exists()
    group_permissions = user.groups.filter(permissions__content_type__model=model).exists()
    return user_permissions or group_permissions


@register.filter
def has_perm(user, arg):
    # split and trim the argument
    app, model, permission_prefix = [x.strip() for x in arg.split(",")]
    if app == "":
        raise ValueError("app name must be provided for has_perm filter")
    if model == "":
        raise ValueError("model name must be provided for has_perm filter")
    if permission_prefix == "":
        raise ValueError("permission prefix must be provided for has_perm filter")
    if user.is_superuser:
        return True
    permission_name = f"{app}.{permission_prefix}_{model}"
    has_permission = user.has_perm(permission_name)
    return has_permission
