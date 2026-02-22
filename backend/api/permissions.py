from __future__ import annotations

from rest_framework.permissions import BasePermission

ADMIN_GROUP_NAME = "admin"
STAFF_OR_ADMIN_PERMISSION_REQUIRED_ERROR = "Staff or 'admin' group permission required"
SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR = "Superuser or 'admin' group permission required"


def is_authenticated_user(user) -> bool:
    return bool(user and user.is_authenticated)


def is_admin_group_member(user) -> bool:
    return bool(is_authenticated_user(user) and user.groups.filter(name=ADMIN_GROUP_NAME).exists())


def is_staff_or_admin_group(user) -> bool:
    return bool(is_authenticated_user(user) and (user.is_staff or is_admin_group_member(user)))


def is_superuser_or_admin_group(user) -> bool:
    return bool(is_authenticated_user(user) and (user.is_superuser or is_admin_group_member(user)))


class IsStaffOrAdminGroup(BasePermission):
    def has_permission(self, request, view):
        return is_staff_or_admin_group(request.user)


class IsSuperuserOrAdminGroup(BasePermission):
    def has_permission(self, request, view):
        return is_superuser_or_admin_group(request.user)
