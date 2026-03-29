"""
FILE_ROLE: Django migration for the core app.

KEY_COMPONENTS:
- seed_admin_menus: Module symbol.
- reverse_seed: Module symbol.
- Migration: Module symbol.

INTERACTIONS:
- Depends on: core app schema/runtime machinery and adjacent services imported by this module.

AI_GUIDELINES:
- Keep command logic thin and delegate real work to services when possible.
- Keep migrations schema-only and reversible; do not add runtime business logic here.
"""

from django.db import migrations


def seed_admin_menus(apps, schema_editor):
    RbacMenuRule = apps.get_model("core", "RbacMenuRule")
    Group = apps.get_model("auth", "Group")

    try:
        admin_group = Group.objects.get(name="admin")
    except Group.DoesNotExist:
        admin_group = None

    admin_menus = [
        "admin",
        "admin-document-types",
        "admin-ai-models",
        "admin-holidays",
        "admin-notifications",
        "admin-backups",
        "admin-server",
        "admin-application-settings",
        "admin-system-costs",
    ]

    # 1. Hide all admin submenus globally (group=None, role="")
    for m in admin_menus:
        RbacMenuRule.objects.get_or_create(menu_id=m, group=None, role="", defaults={"is_visible": False})

    # 2. Add 'admin' group rules
    if admin_group:
        admin_visible_menus = [
            "admin",
            "admin-document-types",
            "admin-holidays",
            "admin-notifications",
            "admin-backups",
            "admin-server",
            "admin-application-settings",
            "admin-system-costs",
        ]
        for m in admin_visible_menus:
            RbacMenuRule.objects.get_or_create(menu_id=m, group=admin_group, role="", defaults={"is_visible": True})

    # 3. Add 'is_staff' role rules
    staff_menus = ["admin", "admin-document-types", "admin-holidays", "admin-notifications"]
    for m in staff_menus:
        RbacMenuRule.objects.get_or_create(menu_id=m, group=None, role="is_staff", defaults={"is_visible": True})

    # 4. Add 'is_superuser' role rules (for admin dashboard visibility, natively superusers bypass everything anyway)
    for m in admin_menus:
        RbacMenuRule.objects.get_or_create(menu_id=m, group=None, role="is_superuser", defaults={"is_visible": True})


def reverse_seed(apps, schema_editor):
    RbacMenuRule = apps.get_model("core", "RbacMenuRule")
    RbacMenuRule.objects.filter(menu_id__startswith="admin").delete()


class Migration(migrations.Migration):

    dependencies = [
        ("core", "0036_alter_rbacfieldrule_unique_together_and_more"),
    ]

    operations = [
        migrations.RunPython(seed_admin_menus, reverse_seed),
    ]
