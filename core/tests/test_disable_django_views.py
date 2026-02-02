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

    @override_settings(MOCK_AUTH_ENABLED=True, DISABLE_DJANGO_VIEWS=True)
    def test_admin_requires_real_login_after_logout_even_with_mock_auth(self):
        """Ensure admin requires real login after logout even when mock auth is enabled"""
        from django.contrib.auth import get_user_model

        User = get_user_model()
        username = "realadmin"
        password = "p4ssword"
        User.objects.create_superuser(username=username, email="a@a.com", password=password)

        # Login as real admin
        logged_in = self.client.login(username=username, password=password)
        self.assertTrue(logged_in)

        # Access admin succeeds
        res1 = self.client.get("/admin/")
        self.assertNotEqual(res1.status_code, 302)

        # Logout using site logout
        self.client.get("/logout/")

        # Now without logging in, admin should redirect to login (not be accessible via mock)
        res2 = self.client.get("/admin/")
        # Should not be 200 - expect redirect to login (302)
        self.assertNotEqual(res2.status_code, 200)
        self.assertIn(res2.status_code, (302, 303))
        loc = res2.headers.get("Location", "")
        self.assertTrue("login" in loc or loc.endswith("/login/"))

    @override_settings(DISABLE_DJANGO_VIEWS=True)
    def test_login_page_uses_simple_layout_when_views_disabled(self):
        """Login page should not render sidebar or topbar when views are disabled"""
        res = self.client.get("/login/")
        content = res.content.decode("utf-8")
        self.assertNotIn('id="sidebar"', content)
        self.assertNotIn('id="navbar-top"', content)
        # Ensure basic bootstrap is present (from bootstrap_base)
        self.assertIn(
            "bootstrap.bundle.min.js", content
        )  # When simple layout is enabled, avoid loading site-specific JS that depends on jQuery
        self.assertNotIn("base_template.js", content)
