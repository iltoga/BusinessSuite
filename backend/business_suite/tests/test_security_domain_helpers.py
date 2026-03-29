"""
FILE_ROLE: Test coverage for business_suite.

KEY_COMPONENTS:
- SecurityDomainHelperTests: Module symbol.

INTERACTIONS:
- Depends on: Django settings/bootstrap and adjacent app services or middleware in this module.

AI_GUIDELINES:
- Keep the file focused on its narrow responsibility and avoid mixing in unrelated business logic.
- Preserve existing runtime contracts for middleware, scripts, or migrations because other code depends on them.
"""

from business_suite.settings.base import _build_https_origins, _default_cookie_domain
from django.test import SimpleTestCase


class SecurityDomainHelperTests(SimpleTestCase):
    def test_cookie_domain_defaults_to_app_domain_for_nested_admin_domain(self):
        self.assertEqual(
            _default_cookie_domain("crm.revisbali.com", "admin.crm.revisbali.com"),
            "crm.revisbali.com",
        )

    def test_cookie_domain_defaults_to_host_only_for_sibling_admin_domain(self):
        self.assertIsNone(_default_cookie_domain("crm.revisbali.com", "crmadmin.revisbali.com"))

    def test_trusted_origins_include_explicit_admin_domain(self):
        self.assertIn(
            "https://crmadmin.revisbali.com",
            _build_https_origins("crm.revisbali.com", "crmadmin.revisbali.com"),
        )
