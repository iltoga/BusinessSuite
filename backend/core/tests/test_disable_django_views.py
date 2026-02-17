from django.test import Client, TestCase, override_settings


class DisableDjangoViewsTests(TestCase):
    def setUp(self):
        self.client = Client()

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_root_redirects_to_admin_when_views_disabled(self):
        """Root path should redirect to /admin/ when DISABLE_DJANGO_VIEWS is True"""
        res = self.client.get("/", follow=False)
        self.assertIn(res.status_code, (302, 303))
        loc = res.headers.get("Location", "")
        self.assertTrue(loc.endswith("/admin/") or "/admin/" in loc, f"Unexpected redirect location: {loc}")

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_admin_allowed(self):
        """Admin path must still be accessible (may be 302->login but must not be 403)"""
        res = self.client.get("/admin/")
        self.assertNotEqual(res.status_code, 403)

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_admin_root_without_slash_allowed(self):
        """Ensure /admin (no trailing slash) is also allowed when views are disabled"""
        res = self.client.get("/admin")
        self.assertNotEqual(res.status_code, 403)

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_api_allowed(self):
        """API paths must not be blocked by the middleware (404 or 200 are acceptable)"""
        res = self.client.get("/api/")
        self.assertNotEqual(res.status_code, 403)

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_login_logout_allowed(self):
        """Ensure /login and /logout are allowed when views are disabled"""
        res1 = self.client.get("/login")
        res2 = self.client.get("/logout")
        self.assertNotEqual(res1.status_code, 403)
        self.assertNotEqual(res2.status_code, 403)

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_login_redirects_to_admin_when_views_disabled(self):
        """POST to /login/ should redirect to /admin/ when DISABLE_DJANGO_VIEWS=True"""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        username = "testlogin"
        password = "p4ssword"
        User.objects.create_user(username=username, password=password)

        res = self.client.post("/login/", {"username": username, "password": password}, follow=False)
        # Expect redirect to admin (302)
        self.assertIn(res.status_code, (302, 303))
        loc = res.headers.get("Location", "")
        self.assertTrue(loc.endswith("/admin/") or "/admin/" in loc, f"Unexpected redirect location: {loc}")
