from django.test import Client, TestCase, override_settings


class DisableDjangoViewsTests(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_root_view_blocked(self):
        """Root path should be blocked when DISABLE_DJANGO_VIEWS is True"""
        res = self.client.get("/")
        self.assertEqual(res.status_code, 403)

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_admin_allowed(self):
        """Admin path must still be accessible (may be 302->login but must not be 403)"""
        res = self.client.get("/admin/")
        self.assertNotEqual(res.status_code, 403)

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_api_allowed(self):
        """API paths must not be blocked by the middleware (404 or 200 are acceptable)"""
        res = self.client.get("/api/")
        self.assertNotEqual(res.status_code, 403)
