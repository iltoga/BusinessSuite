import functools
import logging

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import JsonResponse

from api.async_controls import increment_guard_counter
from api.permissions import is_authenticated_user, is_superuser

User = get_user_model()
logger = logging.getLogger(__name__)
SSE_AUTH_OBSERVABILITY_NAMESPACE = "sse_auth"


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

    def _observe_reject(*, event: str, request, user=None, status_code: int, detail: str):
        counter = increment_guard_counter(namespace=SSE_AUTH_OBSERVABILITY_NAMESPACE, event=event)
        logger.warning(
            "sse_auth event=%s counter=%s status_code=%s path=%s method=%s user_id=%s detail=%s",
            event,
            counter,
            status_code,
            request.path,
            request.method,
            getattr(user, "id", None),
            detail,
        )

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        token_str = _extract_header_token(request)
        user = _resolve_user_from_token(token_str)

        # Fall back to session auth
        if not user and is_authenticated_user(request.user):
            user = request.user

        if user and user.is_active:
            if superuser_only and not is_superuser(user):
                _observe_reject(
                    event="superuser_forbidden_403",
                    request=request,
                    user=user,
                    status_code=403,
                    detail="superuser_required",
                )
                return JsonResponse({"error": "Superuser permission required"}, status=403)
            request.user = user
            return view_func(request, *args, **kwargs)

        _observe_reject(
            event="auth_401",
            request=request,
            user=user,
            status_code=401,
            detail="missing_or_invalid_credentials",
        )
        return JsonResponse({"error": "Authentication required"}, status=401)

    return wrapper
