from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable

from api.async_controls import (
    acquire_enqueue_guard,
    build_user_enqueue_guard_key,
    increment_guard_counter,
    release_enqueue_guard,
)
from api.cache_resilience import is_transient_cache_backend_error
from api.permissions import is_staff_or_admin_group
from django.conf import settings
from rest_framework import pagination, serializers, status
from rest_framework.exceptions import NotFound, ValidationError
from rest_framework.response import Response
from rest_framework.throttling import AnonRateThrottle, ScopedRateThrottle, UserRateThrottle

from api.utils.contracts import build_error_payload

logger = logging.getLogger(__name__)


def _status_code_to_code(status_code: int) -> str:
    if status_code == status.HTTP_400_BAD_REQUEST:
        return "validation_error"
    if status_code == status.HTTP_401_UNAUTHORIZED:
        return "authentication_required"
    if status_code == status.HTTP_403_FORBIDDEN:
        return "forbidden"
    if status_code == status.HTTP_404_NOT_FOUND:
        return "not_found"
    if status_code == status.HTTP_409_CONFLICT:
        return "conflict"
    if status_code == status.HTTP_429_TOO_MANY_REQUESTS:
        return "rate_limited"
    if status_code == status.HTTP_503_SERVICE_UNAVAILABLE:
        return "service_unavailable"
    return "error"


class ResilientThrottleMixin:
    """Fail open when the throttle cache backend is temporarily unavailable."""

    def allow_request(self, request, view):
        try:
            return super().allow_request(request, view)
        except Exception as exc:
            if not is_transient_cache_backend_error(exc):
                raise

            logger.warning(
                "Throttle bypassed for %s %s because the cache backend is temporarily unavailable: %s",
                getattr(request, "method", "?"),
                getattr(getattr(request, "_request", request), "path", "<unknown>"),
                exc,
            )
            self.history = []
            return True


class ResilientAnonRateThrottle(ResilientThrottleMixin, AnonRateThrottle):
    pass


class ResilientUserRateThrottle(ResilientThrottleMixin, UserRateThrottle):
    pass


class ResilientScopedRateThrottle(ResilientThrottleMixin, ScopedRateThrottle):
    pass


class OCRPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for OCR viewset endpoints."""


class DocumentOCRPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for Document OCR viewset endpoints."""


class ComputePlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for Compute viewset endpoints."""


def parse_bool(value, default=False):
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    return str(value).strip().lower() in {"true", "1", "yes", "y", "on"}


def restrict_to_owner_unless_privileged(queryset, user, owner_field: str = "created_by"):
    if is_staff_or_admin_group(user):
        return queryset
    return queryset.filter(**{owner_field: user})


ASYNC_JOB_INFLIGHT_STATUSES = ("pending", "processing")
QUEUE_JOB_INFLIGHT_STATUSES = ("queued", "processing")


def _latest_inflight_job(queryset, statuses):
    return queryset.filter(status__in=statuses).order_by("-created_at", "-id").first()


def _get_enqueue_guard_token(*, namespace: str, user, scope: str | None = None) -> tuple[str, str | None]:
    lock_key = build_user_enqueue_guard_key(
        namespace=namespace,
        user_id=getattr(user, "id", None),
        scope=scope,
    )
    return lock_key, acquire_enqueue_guard(lock_key)


def _observe_async_guard_event(
    *,
    namespace: str,
    event: str,
    user,
    job_id=None,
    status_code: int | None = None,
    detail: str | None = None,
    warning: bool = False,
) -> int:
    counter = increment_guard_counter(namespace=namespace, event=event)
    log_fn = logger.warning if warning else logger.info
    log_fn(
        "async_guard event=%s namespace=%s counter=%s user_id=%s job_id=%s status_code=%s detail=%s",
        event,
        namespace,
        counter,
        getattr(user, "id", None),
        job_id,
        status_code,
        detail or "",
    )
    return counter


class ApiErrorHandlingMixin:
    def error_response(self, message, status_code=status.HTTP_400_BAD_REQUEST, details=None, request=None):
        request = request or getattr(self, "request", None)
        return Response(
            build_error_payload(
                code=status_code and _status_code_to_code(status_code) or "error",
                message=str(message),
                details=details,
                request=request,
            ),
            status=status_code,
        )

    def check_throttles(self, request):
        try:
            return super().check_throttles(request)
        except Exception as exc:
            if not is_transient_cache_backend_error(exc):
                raise

            logger.warning(
                "Skipping throttles for %s %s because the cache backend is temporarily unavailable: %s",
                getattr(request, "method", "?"),
                getattr(getattr(request, "_request", request), "path", "<unknown>"),
                exc,
            )
            return None

    def handle_exception(self, exc):
        from django.db.models.deletion import ProtectedError

        if isinstance(exc, ProtectedError):
            message = exc.args[0] if getattr(exc, "args", None) else "Cannot delete because related objects exist."
            return self.error_response(str(message), status.HTTP_409_CONFLICT)

        if is_transient_cache_backend_error(exc):
            return self.error_response(
                "Service temporarily unavailable while cache services are warming up. Please retry shortly.",
                status.HTTP_503_SERVICE_UNAVAILABLE,
            )

        try:
            response = super().handle_exception(exc)
        except Exception as e:
            import traceback

            if is_transient_cache_backend_error(e):
                return self.error_response(
                    "Service temporarily unavailable while cache services are warming up. Please retry shortly.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            if e.__class__.__name__ == "OperationalError" and "too many clients" in str(e).lower():
                return self.error_response(
                    "Service temporarily unavailable due to high database load. Please retry shortly.",
                    status.HTTP_503_SERVICE_UNAVAILABLE,
                )

            logging.exception("Unhandled exception in API view")
            if settings.DEBUG:
                return self.error_response(
                    f"Server error: {str(e)}",
                    status.HTTP_500_INTERNAL_SERVER_ERROR,
                    details=traceback.format_exc(),
                )
            return self.error_response("Server error", status.HTTP_500_INTERNAL_SERVER_ERROR)

        if response is None:
            if settings.DEBUG:
                return self.error_response("Server error: Response is None", status.HTTP_500_INTERNAL_SERVER_ERROR)
            return self.error_response("Server error", status.HTTP_500_INTERNAL_SERVER_ERROR)
        return response


class StandardResultsSetPagination(pagination.PageNumberPagination):
    page_size = 50
    page_size_query_param = "page_size"
    max_page_size = 200


class CronScopedRateThrottle(ResilientScopedRateThrottle):
    scope = "cron"


class QuickCreateScopedRateThrottle(ResilientScopedRateThrottle):
    scope = "quick_create"


@dataclass
class AsyncEnqueueGuardResult:
    response: Response | None = None
    lock_key: str | None = None
    lock_token: str | None = None
    existing_job: Any | None = None


def prepare_async_enqueue(
    *,
    namespace: str,
    user,
    inflight_queryset,
    inflight_statuses,
    scope: str | None = None,
    busy_message: str,
    deduplicated_response_builder: Callable[[Any], Response],
    error_response_builder: Callable[[str, int], Response],
) -> AsyncEnqueueGuardResult:
    existing_job = _latest_inflight_job(inflight_queryset, inflight_statuses)
    if existing_job:
        _observe_async_guard_event(
            namespace=namespace,
            event="deduplicated",
            user=user,
            job_id=str(existing_job.id),
            status_code=status.HTTP_202_ACCEPTED,
        )
        return AsyncEnqueueGuardResult(response=deduplicated_response_builder(existing_job), existing_job=existing_job)

    lock_key, lock_token = _get_enqueue_guard_token(namespace=namespace, user=user, scope=scope)
    if not lock_token:
        _observe_async_guard_event(
            namespace=namespace,
            event="lock_contention",
            user=user,
            warning=True,
            detail=scope,
        )
        existing_job = _latest_inflight_job(inflight_queryset, inflight_statuses)
        if existing_job:
            _observe_async_guard_event(
                namespace=namespace,
                event="deduplicated",
                user=user,
                job_id=str(existing_job.id),
                status_code=status.HTTP_202_ACCEPTED,
            )
            return AsyncEnqueueGuardResult(response=deduplicated_response_builder(existing_job), existing_job=existing_job)

        _observe_async_guard_event(
            namespace=namespace,
            event="guard_429",
            user=user,
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            warning=True,
            detail=scope,
        )
        return AsyncEnqueueGuardResult(response=error_response_builder(busy_message, status.HTTP_429_TOO_MANY_REQUESTS))

    existing_job = _latest_inflight_job(inflight_queryset, inflight_statuses)
    if existing_job:
        _observe_async_guard_event(
            namespace=namespace,
            event="deduplicated",
            user=user,
            job_id=str(existing_job.id),
            status_code=status.HTTP_202_ACCEPTED,
        )
        release_enqueue_guard(lock_key, lock_token)
        return AsyncEnqueueGuardResult(response=deduplicated_response_builder(existing_job), existing_job=existing_job)

    return AsyncEnqueueGuardResult(lock_key=lock_key, lock_token=lock_token)
