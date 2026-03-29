"""
FILE_ROLE: Defines API permission groups and authorization helpers.

KEY_COMPONENTS:
- is_authenticated_user: Module symbol.
- is_superuser: Module symbol.
- is_admin_group_member: Module symbol.
- is_manager_group_member: Module symbol.
- is_staff_or_admin_group: Module symbol.
- is_superuser_or_admin_group: Module symbol.
- is_admin_or_manager_group: Module symbol.
- IsStaffOrAdminGroup: Module symbol.

INTERACTIONS:
- Depends on: nearby API/core services and DRF helpers used in this module.

AI_GUIDELINES:
- Keep this module focused on reusable API infrastructure rather than domain orchestration.
- Preserve the existing contract so split view modules can import these helpers safely.
"""

from __future__ import annotations

from rest_framework.permissions import BasePermission

ADMIN_GROUP_NAME = "admin"
MANAGER_GROUP_NAME = "manager"
STAFF_OR_ADMIN_PERMISSION_REQUIRED_ERROR = "Staff or 'admin' group permission required"
SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR = "Superuser or 'admin' group permission required"
ADMIN_OR_MANAGER_PERMISSION_REQUIRED_ERROR = "Superuser, 'admin', or 'manager' group permission required"


def is_authenticated_user(user) -> bool:
    return bool(user and user.is_authenticated)


def is_superuser(user) -> bool:
    return bool(is_authenticated_user(user) and user.is_superuser)


def is_admin_group_member(user) -> bool:
    return bool(is_authenticated_user(user) and user.groups.filter(name=ADMIN_GROUP_NAME).exists())


def is_manager_group_member(user) -> bool:
    return bool(is_authenticated_user(user) and user.groups.filter(name=MANAGER_GROUP_NAME).exists())


def is_staff_or_admin_group(user) -> bool:
    return bool(is_authenticated_user(user) and (user.is_staff or is_admin_group_member(user)))


def is_superuser_or_admin_group(user) -> bool:
    return bool(is_superuser(user) or is_admin_group_member(user))


def is_admin_or_manager_group(user) -> bool:
    return bool(is_superuser(user) or is_admin_group_member(user) or is_manager_group_member(user))


class IsStaffOrAdminGroup(BasePermission):
    def has_permission(self, request, view):
        return is_staff_or_admin_group(request.user)


class IsSuperuserOrAdminGroup(BasePermission):
    def has_permission(self, request, view):
        return is_superuser_or_admin_group(request.user)


class IsAdminOrManagerGroup(BasePermission):
    def has_permission(self, request, view):
        return is_admin_or_manager_group(request.user)
