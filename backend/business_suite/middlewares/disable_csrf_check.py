"""
FILE_ROLE: Middleware helper for disabling CSRF checks in targeted flows.

KEY_COMPONENTS:
- DisableCsrfCheckMiddleware: Middleware class.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for middleware, scripts, or migrations because other code depends on them.
"""

from django.utils.deprecation import MiddlewareMixin


class DisableCsrfCheckMiddleware(MiddlewareMixin):
    def process_request(self, req):
        attr = "_dont_enforce_csrf_checks"
        if not getattr(req, attr, False):
            setattr(req, attr, True)
