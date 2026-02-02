from django.conf import settings
from django.http import HttpResponseForbidden

# waffle is optional at runtime in this environment; fall back gracefully
try:
    from waffle import flag_is_active
except Exception:  # pragma: no cover - fallback in CI if waffle isn't installed

    def flag_is_active(request, name):
        return False


# Prefixes that should continue to be served even when Django views are disabled
EXEMPT_PREFIXES = (
    "admin/",
    "nested_admin/",
    "api/",
    "unicorn/",
    "admin-tools/",
    "__debug__/",
    "static/",
    "media/",
)


class DisableDjangoViewsMiddleware:
    """Middleware that prevents access to legacy Django views when feature is disabled.

    Behavior:
    - If the environment setting `DISABLE_DJANGO_VIEWS` is True, or the waffle flag
      `disable_django_views` is active, requests to non-exempt prefixes will return 403.
    - Admin, API, nested admin and a few other prefixes are always allowed.
    """

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        disable_setting = getattr(settings, "DISABLE_DJANGO_VIEWS", False)
        waffle_flag = False
        try:
            waffle_flag = flag_is_active(request, "disable_django_views")
        except Exception:
            waffle_flag = False

        should_disable = bool(disable_setting or waffle_flag)
        path = (request.path_info or "").lstrip("/")

        if should_disable and not any(path.startswith(p) for p in EXEMPT_PREFIXES):
            return HttpResponseForbidden("Django views are currently disabled")

        return self.get_response(request)
