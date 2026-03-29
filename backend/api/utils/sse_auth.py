"""Authentication helpers for SSE endpoints and token validation."""

import functools
import inspect
import logging

from api.async_controls import increment_guard_counter
from api.permissions import is_authenticated_user, is_superuser
from api.utils.contracts import build_error_payload
from asgiref.sync import sync_to_async
from business_suite.authentication import JwtOrMockAuthentication, ensure_mock_user
from django.contrib.auth import get_user_model
from django.http import HttpRequest, JsonResponse
from rest_framework.authtoken.models import Token

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

    def _extract_header_token(http_request: HttpRequest):
        auth_header = (http_request.META.get("HTTP_AUTHORIZATION") or "").strip()
        if not auth_header:
            return None

        parts = auth_header.split(" ", 1)
        if len(parts) == 2 and parts[0].lower() in {"bearer", "token"}:
            return parts[1].strip() or None
        return auth_header

    def _resolve_user_from_request(http_request: HttpRequest, token_str):
        if token_str == "mock-token":
            try:
                user = ensure_mock_user()
            except Exception:
                return None
            return user if user.is_active else None

        authenticator = JwtOrMockAuthentication()
        try:
            result = authenticator.authenticate(http_request)
        except Exception:
            result = None
        if result:
            return result[0]

        if not token_str:
            return None

        try:
            token = Token.objects.select_related("user").get(key=token_str)
        except Token.DoesNotExist:
            return None

        user = token.user
        return user if user and user.is_active else None

    def _observe_reject(*, event: str, http_request: HttpRequest, user=None, status_code: int, detail: str):
        counter = increment_guard_counter(namespace=SSE_AUTH_OBSERVABILITY_NAMESPACE, event=event)
        logger.warning(
            "sse_auth event=%s counter=%s status_code=%s path=%s method=%s user_id=%s detail=%s",
            event,
            counter,
            status_code,
            http_request.path,
            http_request.method,
            getattr(user, "id", None),
            detail,
        )

    def _resolve_authenticated_user(http_request: HttpRequest):
        token_str = _extract_header_token(http_request)
        user = _resolve_user_from_request(http_request, token_str) if token_str else None

        # Fall back to session auth
        if not user and is_authenticated_user(http_request.user):
            user = http_request.user
        return user

    def _reject_auth(http_request: HttpRequest, *, user=None):
        _observe_reject(
            event="auth_401",
            http_request=http_request,
            user=user,
            status_code=401,
            detail="missing_or_invalid_credentials",
        )
        return JsonResponse(
            build_error_payload(
                code="authentication_required",
                message="Authentication required",
                request=http_request,
            ),
            status=401,
        )

    def _reject_superuser(http_request: HttpRequest, *, user):
        _observe_reject(
            event="superuser_forbidden_403",
            http_request=http_request,
            user=user,
            status_code=403,
            detail="superuser_required",
        )
        return JsonResponse(
            build_error_payload(
                code="forbidden",
                message="Superuser permission required",
                request=http_request,
            ),
            status=403,
        )

    if inspect.iscoroutinefunction(view_func):

        @functools.wraps(view_func)
        async def async_wrapper(http_request: HttpRequest, *args, **kwargs):
            user = await sync_to_async(_resolve_authenticated_user, thread_sensitive=True)(http_request)

            if user and user.is_active:
                if superuser_only and not is_superuser(user):
                    return _reject_superuser(http_request, user=user)
                http_request.user = user
                return await view_func(http_request, *args, **kwargs)

            return _reject_auth(http_request, user=user)

        return async_wrapper

    @functools.wraps(view_func)
    def wrapper(http_request: HttpRequest, *args, **kwargs):
        user = _resolve_authenticated_user(http_request)

        if user and user.is_active:
            if superuser_only and not is_superuser(user):
                return _reject_superuser(http_request, user=user)
            http_request.user = user
            return view_func(http_request, *args, **kwargs)

        return _reject_auth(http_request, user=user)

    return wrapper
