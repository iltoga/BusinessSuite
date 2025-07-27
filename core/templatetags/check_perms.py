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
    app, model, permission_prefix = [x.strip() for x in arg.split(',')]
    if app == '':
        raise ValueError("app name must be provided for has_perm filter")
    if model == '':
        raise ValueError("model name must be provided for has_perm filter")
    if permission_prefix == '':
        raise ValueError("permission prefix must be provided for has_perm filter")
    if user.is_superuser:
        return True
    permission_name = f"{app}.{permission_prefix}_{model}"
    print(f"checking for permission: {permission_name}")
    has_permission = user.has_perm(permission_name)
    print(f"user has permission: {has_permission}")
    return has_permission


