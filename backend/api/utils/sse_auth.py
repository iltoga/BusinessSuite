import functools
import json

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse

User = get_user_model()


def sse_token_auth_required(view_func=None, superuser_only=False):
    """
    Decorator for SSE endpoints that need token auth.
    EventSource cannot send Authorization headers, so we accept token via query param.
    """
    if view_func is None:
        return functools.partial(sse_token_auth_required, superuser_only=superuser_only)

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check for token in query param first (for EventSource)
        token_str = request.GET.get("token")
        user = None
        if token_str:
            # Try mock token first if enabled
            if getattr(settings, "MOCK_AUTH_ENABLED", False) and token_str == "mock-token":
                from business_suite.authentication import ensure_mock_user

                user = ensure_mock_user()

            # Try JWT token first
            elif token_str.startswith("eyJ"):
                try:
                    from rest_framework_simplejwt.tokens import AccessToken

                    access_token = AccessToken(token_str)
                    user_id = access_token.get("user_id")
                    user = User.objects.get(pk=user_id)
                except Exception:
                    pass
            else:
                # Try DRF Token auth
                try:
                    from rest_framework.authtoken.models import Token

                    token = Token.objects.select_related("user").get(key=token_str)
                    user = token.user
                except Exception:
                    pass

        # Fall back to session auth
        if not user and request.user.is_authenticated:
            user = request.user

        if user and user.is_active:
            if superuser_only and not user.is_superuser:
                return JsonResponse({"error": "Superuser permission required"}, status=403)
            request.user = user
            return view_func(request, *args, **kwargs)

        return JsonResponse({"error": "Authentication required"}, status=401)

    return wrapper
