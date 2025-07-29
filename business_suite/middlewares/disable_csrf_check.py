from django.utils.deprecation import MiddlewareMixin

import re
from django.conf import settings

EXEMPT_URLS = [re.compile(url) for url in settings.LOGIN_EXEMPT_URLS]

class DisableCsrfCheckMiddleware(MiddlewareMixin):
    def process_request(self, req):
        attr = '_dont_enforce_csrf_checks'
        if not getattr(req, attr, False):
            setattr(req, attr, True)
