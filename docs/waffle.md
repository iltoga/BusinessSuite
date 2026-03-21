# django-waffle Feature Flags

This project uses `django-waffle` for runtime feature toggles.

## Active usage in current codebase

The `disable_django_views` flag and its associated middleware (`DisableDjangoViewsMiddleware`) have been **removed**.
Legacy Django template views were removed from the codebase entirely.

Related environment fallback:

- `DISABLE_DJANGO_VIEWS` setting is no longer referenced in middleware.

Status: **No waffle flags are actively used in middleware.** Waffle remains available for future runtime feature toggles via Django Admin.

## When to use a flag vs env var

- Use **Waffle flag** when runtime on/off control is needed without redeploy.
- Use **env var** for deployment-level defaults and safer boot-time behavior.
- Middleware currently supports both and treats either as disabling legacy views.

## Admin workflow

1. Open Django Admin.
2. Go to `Waffle -> Flags`.
3. Create or edit `disable_django_views`.
4. Set `Everyone` to:
   - `Yes`: force disabled legacy views
   - `No`: force enabled legacy views
   - `Unknown`: evaluate per-user/group/rollout criteria

## Shell workflow

```python
python backend/manage.py shell
from waffle.models import Flag

Flag.objects.update_or_create(
    name='disable_django_views',
    defaults={'everyone': True},
)
```

## Testing guidance

- In middleware/API tests, verify both toggles:
  - `override_settings(DISABLE_DJANGO_VIEWS=True/False)`
  - Waffle flag active/inactive path
- Keep tests resilient if waffle import is unavailable (middleware has fallback behavior).

## Notes

- Keep the list of actively used flags short and documented.
- Remove stale flags from admin when no longer referenced in code.
