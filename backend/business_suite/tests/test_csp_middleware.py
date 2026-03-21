"""Tests for the Django 6 CSP middleware integration in settings.

Validates that:
- CSP is disabled by default (no header emitted, middleware absent).
- When CSP_ENABLED=True + CSP_MODE=report-only, only the Report-Only header is set.
- When CSP_ENABLED=True + CSP_MODE=enforce, the enforcing header is set.
- Nonces are generated per-request and appear in the header when accessed.
- Cloudflare challenge domain is always present in frame-src.
- CSP_REPORT_URI appears in the policy when configured.
- When nonce is not accessed, CSP.NONCE sentinels are stripped from the policy.
"""

from django.http import HttpResponse
from django.middleware.csp import ContentSecurityPolicyMiddleware, get_nonce
from django.test import RequestFactory, SimpleTestCase, override_settings
from django.utils.csp import CSP


def _get_response(_request):
    return HttpResponse("ok")


def _get_response_with_nonce(request):
    """Simulates a view/template that accesses the CSP nonce (like {{ csp_nonce }})."""
    nonce = get_nonce(request)
    str(nonce)  # force LazyNonce evaluation (Django only injects nonce when accessed)
    return HttpResponse("ok")


class CspMiddlewareDisabledTests(SimpleTestCase):
    """CSP disabled (default): middleware should not add any CSP header."""

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY={})
    def test_no_csp_headers_when_disabled(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        self.assertNotIn("Content-Security-Policy", response)
        self.assertNotIn("Content-Security-Policy-Report-Only", response)


class CspMiddlewareReportOnlyTests(SimpleTestCase):
    """CSP_MODE=report-only: policy goes into SECURE_CSP_REPORT_ONLY."""

    REPORT_ONLY_POLICY = {
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF, CSP.NONCE, "https://static.cloudflareinsights.com"],
        "style-src": [CSP.SELF, CSP.NONCE, CSP.UNSAFE_INLINE],
        "img-src": [CSP.SELF, "data:", "blob:"],
        "font-src": [CSP.SELF, "data:"],
        "connect-src": [CSP.SELF, "https://cloudflareinsights.com"],
        "frame-src": [CSP.SELF, "https://challenges.cloudflare.com"],
        "object-src": [CSP.NONE],
        "base-uri": [CSP.SELF],
        "form-action": [CSP.SELF],
        "frame-ancestors": [CSP.SELF],
        "upgrade-insecure-requests": True,
    }

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_report_only_header_present(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        self.assertIn("Content-Security-Policy-Report-Only", response)
        self.assertNotIn("Content-Security-Policy", response)

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_nonce_appears_in_report_only_header(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response_with_nonce)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertRegex(header, r"'nonce-[A-Za-z0-9+/=_-]+'")

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_nonce_stripped_when_not_accessed(self):
        """When no view/template accesses the nonce, the sentinel is removed."""
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertNotIn("nonce-", header)
        # script-src should still have 'self' but no nonce
        self.assertIn("script-src 'self'", header)

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_cloudflare_in_frame_src(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertIn("https://challenges.cloudflare.com", header)

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_cloudflare_web_analytics_sources_allowed(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertIn("https://static.cloudflareinsights.com", header)
        self.assertIn("https://cloudflareinsights.com", header)

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_self_in_default_src(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertIn("default-src 'self'", header)

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=REPORT_ONLY_POLICY)
    def test_object_src_none(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertIn("object-src 'none'", header)


class CspMiddlewareEnforceTests(SimpleTestCase):
    """CSP_MODE=enforce: policy goes into SECURE_CSP."""

    ENFORCE_POLICY = {
        "default-src": [CSP.SELF],
        "script-src": [CSP.SELF, CSP.NONCE, "https://static.cloudflareinsights.com"],
        "style-src": [CSP.SELF, CSP.NONCE, CSP.UNSAFE_INLINE],
        "img-src": [CSP.SELF, "data:", "blob:"],
        "font-src": [CSP.SELF, "data:"],
        "connect-src": [CSP.SELF, "https://cloudflareinsights.com"],
        "frame-src": [CSP.SELF, "https://challenges.cloudflare.com"],
        "object-src": [CSP.NONE],
        "base-uri": [CSP.SELF],
        "form-action": [CSP.SELF],
        "frame-ancestors": [CSP.SELF],
        "upgrade-insecure-requests": True,
    }

    @override_settings(SECURE_CSP=ENFORCE_POLICY, SECURE_CSP_REPORT_ONLY={})
    def test_enforce_header_present(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        self.assertIn("Content-Security-Policy", response)
        self.assertNotIn("Content-Security-Policy-Report-Only", response)

    @override_settings(SECURE_CSP=ENFORCE_POLICY, SECURE_CSP_REPORT_ONLY={})
    def test_nonce_appears_in_enforce_header(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response_with_nonce)
        response = mw(request)
        header = response["Content-Security-Policy"]
        self.assertRegex(header, r"'nonce-[A-Za-z0-9+/=_-]+'")

    @override_settings(SECURE_CSP=ENFORCE_POLICY, SECURE_CSP_REPORT_ONLY={})
    def test_upgrade_insecure_requests_directive(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy"]
        self.assertIn("upgrade-insecure-requests", header)


class CspMiddlewareReportUriTests(SimpleTestCase):
    """CSP_REPORT_URI is included in the policy when configured."""

    POLICY_WITH_REPORT_URI = {
        "default-src": [CSP.SELF],
        "report-uri": "https://example.com/csp-report",
    }

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=POLICY_WITH_REPORT_URI)
    def test_report_uri_in_header(self):
        request = RequestFactory().get("/")
        mw = ContentSecurityPolicyMiddleware(_get_response)
        response = mw(request)
        header = response["Content-Security-Policy-Report-Only"]
        self.assertIn("report-uri https://example.com/csp-report", header)


class CspNonceUniquenessTests(SimpleTestCase):
    """Each request gets a unique nonce."""

    POLICY = {
        "script-src": [CSP.SELF, CSP.NONCE],
    }

    @override_settings(SECURE_CSP={}, SECURE_CSP_REPORT_ONLY=POLICY)
    def test_nonces_differ_between_requests(self):
        import re

        mw = ContentSecurityPolicyMiddleware(_get_response_with_nonce)
        nonces = set()
        for _ in range(5):
            request = RequestFactory().get("/")
            response = mw(request)
            header = response["Content-Security-Policy-Report-Only"]
            match = re.search(r"'nonce-([A-Za-z0-9+/=_-]+)'", header)
            self.assertIsNotNone(match)
            nonces.add(match.group(1))
        self.assertEqual(len(nonces), 5, "Expected 5 unique nonces")


class CspSettingsIntegrationTests(SimpleTestCase):
    """Verify the settings module builds the correct CSP config based on env vars."""

    def test_default_csp_disabled(self):
        """With default env (CSP_ENABLED=False), both settings dicts are empty."""
        from django.conf import settings

        # Default should be disabled (no CSP)
        self.assertFalse(getattr(settings, "CSP_ENABLED", True))
        self.assertEqual(getattr(settings, "SECURE_CSP", None), {})
        self.assertEqual(getattr(settings, "SECURE_CSP_REPORT_ONLY", None), {})

    def test_csp_context_processor_registered(self):
        """The csp context processor should always be registered."""
        from django.conf import settings

        processors = settings.TEMPLATES[0]["OPTIONS"]["context_processors"]
        self.assertIn("django.template.context_processors.csp", processors)
