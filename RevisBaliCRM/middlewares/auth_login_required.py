import re

from django.conf import settings
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin

EXEMPT_URLS = [re.compile(url) for url in settings.LOGIN_EXEMPT_URLS]


class AuthLoginRequiredMiddleware(MiddlewareMixin):
    """Middleware to require login for all views."""

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if not response:
            response = self.get_response(request)
        return response

    def process_request(self, request):
        assert hasattr(
            request, "user"
        ), """The AuthLoginRequiredMiddleware requires authentication middleware to be installed.
        Edit your MIDDLEWARE setting to insert 'django.contrib.auth.middleware.AuthenticationMiddleware'.
        If that doesn't work, ensure your TEMPLATE_CONTEXT_PROCESSORS setting
        includes 'django.core.context_processors.auth'."""

        if not request.user.is_authenticated:
            path = request.path_info.lstrip("/")
            if not any(m.match(path) for m in EXEMPT_URLS):
                return redirect(settings.LOGIN_URL)
