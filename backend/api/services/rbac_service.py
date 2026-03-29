"""RBAC service helpers for evaluating and persisting role-based rules."""

import logging
from typing import Any

from core.models.rbac_rule import RbacFieldRule, RbacMenuRule
from django.contrib.auth.models import User
from django.core.cache import cache
from django.db.models import Q

logger = logging.getLogger(__name__)


def get_user_rbac_claims(user: User) -> dict[str, dict[str, Any]]:
    """
    Evaluates RbacMenuRule and RbacFieldRule for the given user.
    Returns a unified dictionary representing the user's evaluated permissions.

    Priority:
    1. Superuser: always full access (even if explicit rules deny access).
    2. Group-specific rules: highest priority. If a user belongs to multiple groups
       and they conflict, we apply an OR logic (if any group permits it, it's permitted).
    3. Global rules (group__isnull=True): fallback if no group-specific rule exists.
    """
    if not user.is_authenticated:
        return {"menus": {}, "fields": {}}

    cache_key = f"rbac_claims_{user.id}"
    cached = cache.get(cache_key)
    if cached is not None:
        return cached

    menus: dict[str, bool] = {}
    fields: dict[str, dict[str, bool]] = {}

    user_groups = list(user.groups.all())
    user_roles = []
    if user.is_staff:
        user_roles.append("is_staff")
    if user.is_superuser:
        user_roles.append("is_superuser")

    # --- MENU RULES ---
    # 1. Fetch globals
    global_menu_rules = {
        rule.menu_id: rule.is_visible for rule in RbacMenuRule.objects.filter(group__isnull=True, role="")
    }

    # 2. Fetch specific
    specific_menu_rules = RbacMenuRule.objects.filter(Q(group__in=user_groups) | Q(role__in=user_roles))
    # Group by menu_id to apply OR logic across multiple groups/roles
    menu_overrides: dict[str, bool] = {}
    for rule in specific_menu_rules:
        # If any of the user's groups grants visibility, they can see it
        menu_overrides[rule.menu_id] = menu_overrides.get(rule.menu_id, False) or rule.is_visible

    # Merge
    all_menu_ids = set(global_menu_rules.keys()).union(menu_overrides.keys())
    for mid in all_menu_ids:
        if user.is_superuser:
            menus[mid] = True
        elif mid in menu_overrides:
            menus[mid] = menu_overrides[mid]
        else:
            menus[mid] = global_menu_rules.get(mid, True)

    # --- FIELD RULES ---
    global_field_rules = {
        f"{rule.model_name}.{rule.field_name}": {"can_read": rule.can_read, "can_write": rule.can_write}
        for rule in RbacFieldRule.objects.filter(group__isnull=True, role="")
    }

    specific_field_rules = RbacFieldRule.objects.filter(Q(group__in=user_groups) | Q(role__in=user_roles))
    field_overrides: dict[str, dict[str, bool]] = {}

    for rule in specific_field_rules:
        key = f"{rule.model_name}.{rule.field_name}"
        if key not in field_overrides:
            field_overrides[key] = {"can_read": False, "can_write": False}
        field_overrides[key]["can_read"] = field_overrides[key]["can_read"] or rule.can_read
        field_overrides[key]["can_write"] = field_overrides[key]["can_write"] or rule.can_write

    all_field_keys = set(global_field_rules.keys()).union(field_overrides.keys())
    for fid in all_field_keys:
        if user.is_superuser:
            fields[fid] = {"can_read": True, "can_write": True}
        elif fid in field_overrides:
            fields[fid] = field_overrides[fid]
        else:
            fields[fid] = global_field_rules.get(fid, {"can_read": True, "can_write": True})

    result = {"menus": menus, "fields": fields}

    # Cache for 5 minutes. Cache invalidate on signal could be added if instant updates are needed.
    cache.set(cache_key, result, timeout=300)

    return result
