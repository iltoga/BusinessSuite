from django.contrib.auth import get_user_model
from django.contrib.auth.models import AnonymousUser
from django.core.cache import cache
from django.http import JsonResponse
from django.test import RequestFactory, TestCase

from api.async_controls import build_guard_counter_key
from api.utils.sse_auth import sse_token_auth_required

User = get_user_model()


class SSEAuthObservabilityTests(TestCase):
    def setUp(self):
        cache.clear()
        self.factory = RequestFactory()

    def tearDown(self):
        cache.clear()

    def _build_view(self, *, superuser_only: bool = False):
        @sse_token_auth_required(superuser_only=superuser_only)
        def _view(_request):
            return JsonResponse({"ok": True})

        return _view

    def test_unauthenticated_reject_increments_observability_counter(self):
        view = self._build_view()
        request = self.factory.get("/api/test-sse-auth/")
        request.user = AnonymousUser()

        response = view(request)

        self.assertEqual(response.status_code, 401)
        key = build_guard_counter_key(namespace="sse_auth", event="auth_401")
        self.assertEqual(cache.get(key), 1)

    def test_superuser_only_reject_increments_observability_counter(self):
        view = self._build_view(superuser_only=True)
        request = self.factory.get("/api/test-sse-auth/")
        request.user = User.objects.create_user("staff-user", "staff-user@example.com", "pass", is_staff=True)

        response = view(request)

        self.assertEqual(response.status_code, 403)
        key = build_guard_counter_key(namespace="sse_auth", event="superuser_forbidden_403")
        self.assertEqual(cache.get(key), 1)
