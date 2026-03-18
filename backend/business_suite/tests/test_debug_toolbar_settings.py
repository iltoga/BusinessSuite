import importlib
import os

from django.conf import settings
from django.test import SimpleTestCase, override_settings
from django.urls import clear_url_caches


class DebugToolbarSettingsTests(SimpleTestCase):
    def _load_settings_snapshot(
        self,
        *,
        module_name: str,
        env_updates: dict[str, str | None],
        fields: list[str],
    ) -> dict[str, object]:
        module = importlib.import_module(module_name)
        originals = {key: os.environ.get(key) for key in env_updates}

        try:
            for key, value in env_updates.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

            importlib.reload(importlib.import_module("business_suite.settings.base"))
            reloaded = importlib.reload(module)
            return {field: getattr(reloaded, field) for field in fields}
        finally:
            for key, value in originals.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value

            importlib.reload(importlib.import_module("business_suite.settings.base"))
            importlib.reload(module)

    def test_base_settings_parse_debug_bool_case_insensitively(self):
        snapshot = self._load_settings_snapshot(
            module_name="business_suite.settings.base",
            env_updates={"DJANGO_DEBUG": "true"},
            fields=["DEBUG"],
        )

        self.assertIs(snapshot["DEBUG"], True)

    def test_dev_settings_skip_debug_toolbar_when_debug_false(self):
        snapshot = self._load_settings_snapshot(
            module_name="business_suite.settings.dev",
            env_updates={
                "DJANGO_SETTINGS_MODULE": "business_suite.settings.dev",
                "DJANGO_DEBUG": "False",
                "ENABLE_DEBUG_TOOLBAR": "True",
            },
            fields=["DEBUG", "ENABLE_DEBUG_TOOLBAR", "INSTALLED_APPS", "MIDDLEWARE"],
        )

        self.assertIs(snapshot["DEBUG"], False)
        self.assertIs(snapshot["ENABLE_DEBUG_TOOLBAR"], False)
        self.assertNotIn("debug_toolbar", snapshot["INSTALLED_APPS"])
        self.assertNotIn("debug_toolbar.middleware.DebugToolbarMiddleware", snapshot["MIDDLEWARE"])
        self.assertIn(
            "business_suite.middlewares.disable_csrf_check.DisableCsrfCheckMiddleware",
            snapshot["MIDDLEWARE"],
        )
        self.assertIn("cache.middleware.CacheMiddleware", snapshot["MIDDLEWARE"])
        self.assertIn("waffle.middleware.WaffleMiddleware", snapshot["MIDDLEWARE"])

    def test_urls_skip_debug_toolbar_when_feature_disabled(self):
        import business_suite.urls as urls_module

        installed_apps = [app for app in settings.INSTALLED_APPS if app != "debug_toolbar"]

        with override_settings(ENABLE_DEBUG_TOOLBAR=False, INSTALLED_APPS=installed_apps):
            clear_url_caches()
            reloaded = importlib.reload(urls_module)
            routes = [getattr(pattern.pattern, "_route", str(pattern.pattern)) for pattern in reloaded.urlpatterns]

            self.assertNotIn("__debug__/", routes)

        clear_url_caches()
        importlib.reload(urls_module)
