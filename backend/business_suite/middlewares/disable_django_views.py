from django.conf import settings
from django.http import HttpResponseForbidden

# waffle is optional at runtime in this environment; fall back gracefully
try:
    from waffle import flag_is_active
except Exception:  # pragma: no cover - fallback in CI if waffle isn't installed

    def flag_is_active(request, name):
        return False


# Prefixes that should continue to be served even when Django views are disabled
# Values are prefix roots (no trailing slash). Matching allows either the exact
# prefix or the prefix followed by a slash (e.g., 'admin' or 'admin/').
EXEMPT_PREFIXES = (
    "admin",
    "nested_admin",
    "api",
    "__debug__",
    "static",
    "staticfiles",
    "media",
    "uploads",
    # Keep auth routes available even when Django views are disabled
    "login",
    "logout",
)


def _is_exempt_path(path: str) -> bool:
    """Return True if the incoming path belongs to an exempt prefix.

    This matches both the root prefix (e.g., 'admin') and any nested
    paths (e.g., 'admin/' and 'admin/users').
    """
    for p in EXEMPT_PREFIXES:
        if path == p or path.startswith(p + "/"):
            return True
    return False


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

        # If views are disabled, allow the root path to redirect to admin
        # instead of returning 403. This ensures a safe default route exists
        # that stays accessible even when the rest of the Django views are off.
        if should_disable and path == "":
            from django.shortcuts import redirect

            return redirect("/admin/")

        if should_disable and not _is_exempt_path(path):
            return HttpResponseForbidden("Django views are currently disabled")

        return self.get_response(request)
