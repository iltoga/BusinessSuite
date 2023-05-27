from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin
from django.contrib.auth.decorators import login_required
from django.urls import reverse

import re
from django.conf import settings

EXEMPT_URLS = [re.compile(url) for url in settings.LOGIN_EXEMPT_URLS]

class DisableCsrfCheck(MiddlewareMixin):
    def process_request(self, req):
        attr = '_dont_enforce_csrf_checks'
        if not getattr(req, attr, False):
            setattr(req, attr, True)

class LoginRequiredMiddleware(MiddlewareMixin):
    """ Middleware to require login for all views. """
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        response = self.process_request(request)
        if not response:
            response = self.get_response(request)
        return response

    def process_request(self, request):
        assert hasattr(request, 'user'), "The Django authentication middleware requires the authentication middleware to be installed. Edit your MIDDLEWARE setting to insert 'django.contrib.auth.middleware.AuthenticationMiddleware' before 'LoginRequiredMiddleware'."

        if not request.user.is_authenticated:
            path = request.path_info.lstrip('/')
            if not any(m.match(path) for m in EXEMPT_URLS):
                return redirect(settings.LOGIN_URL)