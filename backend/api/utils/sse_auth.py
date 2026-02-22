import functools

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse

User = get_user_model()


def sse_token_auth_required(view_func=None, superuser_only=False):
    """
    Decorator for SSE endpoints that need auth.

    Preferred auth is Authorization header (Bearer/Token).
    """
    if view_func is None:
        return functools.partial(sse_token_auth_required, superuser_only=superuser_only)

    def _extract_header_token(request):
        auth_header = (request.META.get("HTTP_AUTHORIZATION") or "").strip()
        if not auth_header:
            return None

        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in {"bearer", "token"}:
            return parts[1].strip() or None
        return auth_header

    def _resolve_user_from_token(token_str):
        if not token_str:
            return None

        if getattr(settings, "MOCK_AUTH_ENABLED", False) and token_str == "mock-token":
            from business_suite.authentication import ensure_mock_user

            return ensure_mock_user()

        if token_str.startswith("eyJ"):
            try:
                from rest_framework_simplejwt.tokens import AccessToken

                access_token = AccessToken(token_str)
                user_id = access_token.get("user_id")
                return User.objects.get(pk=user_id)
            except Exception:
                pass

        try:
            from rest_framework.authtoken.models import Token

            token = Token.objects.select_related("user").get(key=token_str)
            return token.user
        except Exception:
            return None

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token_str = _extract_header_token(request)
        user = _resolve_user_from_token(token_str)

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
