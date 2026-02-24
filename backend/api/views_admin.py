# Admin Tools API ViewSets
import datetime
import functools
import json
import logging
import os
import shutil
import tarfile

import requests
from admin_tools import services
from api.permissions import (
    SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR,
    IsSuperuserOrAdminGroup,
    is_superuser_or_admin_group,
)
from api.utils.sse_auth import sse_token_auth_required
from api.views import ApiErrorHandlingMixin
from core.models.ai_request_usage import AIRequestUsage
from core.services.ai_usage_service import AIUsageFeature
from django.conf import settings
from django.contrib.auth import get_user_model
from django.contrib.staticfiles import finders
from django.core.cache import caches
from django.db.models import Count, Q, Sum
from django.db.utils import OperationalError, ProgrammingError
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from django.utils import timezone
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

User = get_user_model()
logger = logging.getLogger(__name__)


class BackupsPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for backup utility endpoints."""


class ServerManagementPlaceholderSerializer(serializers.Serializer):
    """Schema placeholder for server management utility endpoints."""


def _clear_cacheops_query_store() -> None:
    """
    Purge cacheops query cache.

    Cacheops uses a dedicated Redis DB configured by `CACHEOPS_REDIS`, so
    global cache clears must invalidate both Django default cache and cacheops.
    """
    from cacheops import invalidate_all

    invalidate_all()


# ============================================================================
# Plain Django views for SSE endpoints (bypass DRF content negotiation)
# ============================================================================


@sse_token_auth_required()
def backup_start_sse(request):
    """SSE endpoint for backup - bypasses DRF content negotiation."""
    if not is_superuser_or_admin_group(request.user):
        return JsonResponse({"error": SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR}, status=403)

    include_users = request.GET.get("include_users", "0") in ("1", "true", "True")

    def _sse_event(data: str):
        return f"data: {json.dumps({'message': data})}\n\n"

    def event_stream():
        yield _sse_event("Backup started")
        try:
            for msg in services.backup_all(include_users=include_users):
                yield ": keepalive\n\n"
                if msg.startswith("RESULT_PATH:"):
                    path = msg.split(":", 1)[1]
                    yield _sse_event(f"Backup finished: {path}")
                else:
                    yield _sse_event(msg)
        except Exception as ex:
            yield _sse_event(f"Error: {str(ex)}")

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


@sse_token_auth_required()
def backup_restore_sse(request):
    """SSE endpoint for restore - bypasses DRF content negotiation."""
    if not is_superuser_or_admin_group(request.user):
        return JsonResponse({"error": SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR}, status=403)

    filename = request.GET.get("file")
    if not filename:
        return JsonResponse({"error": "Missing file parameter"}, status=400)

    gz_path = os.path.join(services.BACKUPS_DIR, filename)
    include_users = request.GET.get("include_users", "0") in ("1", "true", "True")

    def _sse_event(data: str):
        return f"data: {json.dumps({'message': data})}\n\n"

    def event_stream():
        yield _sse_event("Restore started")
        try:
            for msg in services.restore_from_file(gz_path, include_users=include_users):
                yield ": keepalive\n\n"
                if msg.startswith("PROGRESS:"):
                    progress = msg.split(":")[1]
                    yield f"data: {json.dumps({'progress': progress})}\n\n"
                else:
                    yield _sse_event(msg)
            yield _sse_event("Restore finished")
        except Exception as ex:
            yield _sse_event(f"Error: {str(ex)}")

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


# ============================================================================
# DRF ViewSets for REST API endpoints
# ============================================================================


class BackupsViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    serializer_class = BackupsPlaceholderSerializer
    permission_classes = [IsAuthenticated, IsSuperuserOrAdminGroup]

    def _parse_backup_datetime(self, filename: str, path: str | None = None) -> datetime.datetime | None:
        """Parse datetime from backup filename like backup-20260131-045527.tar.zst
        Returns a timezone-aware datetime.
        """
        import re

        patterns: list[tuple[str, datetime.tzinfo | None]] = [
            # Generated by services.backup_all(), stamped with utcnow().
            (r"^backup-(\d{8})-(\d{6})", datetime.timezone.utc),
            # Generated by upload endpoint, stamped in Django local timezone.
            (r"^uploaded-(\d{8})-(\d{6})", timezone.get_current_timezone()),
            # Fallback: legacy/unknown names assumed UTC.
            (r"(\d{8})-(\d{6})", datetime.timezone.utc),
        ]

        for pattern, tzinfo in patterns:
            match = re.search(pattern, filename)
            if not match:
                continue
            date_str = match.group(1)
            time_str = match.group(2)
            try:
                naive_dt = datetime.datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                if tzinfo is None:
                    return naive_dt
                return timezone.make_aware(naive_dt, tzinfo)
            except ValueError:
                continue

        # Last-resort fallback: file mtime.
        if path:
            try:
                modified_ts = os.path.getmtime(path)
                return datetime.datetime.fromtimestamp(modified_ts, tz=datetime.timezone.utc)
            except OSError:
                return None
        return None

    @extend_schema(summary="List available backups", responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        """List local backups with metadata."""
        backups: list[dict] = []
        sort_floor = datetime.datetime.min.replace(tzinfo=datetime.timezone.utc)
        sortable_backups: list[tuple[datetime.datetime, dict]] = []
        backups_dir = services.BACKUPS_DIR
        if os.path.exists(backups_dir):
            for fn in os.listdir(backups_dir):
                path = os.path.join(backups_dir, fn)
                try:
                    size = os.path.getsize(path)
                except Exception:
                    size = None

                btype = (
                    "tar.zst"
                    if fn.endswith(".tar.zst")
                    else (
                        "tar.gz"
                        if fn.endswith(".tar.gz") or fn.endswith(".tgz")
                        else ("json.gz" if fn.endswith(".gz") else "json")
                    )
                )
                included_files = None
                if btype in ("tar.gz", "tar.zst"):
                    try:
                        comp = "zst" if btype == "tar.zst" else "gz"
                        with tarfile.open(path, f"r:{comp}") as tar:
                            try:
                                member = tar.getmember("manifest.json")
                                f = tar.extractfile(member)
                                if f:
                                    manifest = json.load(f)
                                    included_files = manifest.get("included_files_count")
                            except KeyError:
                                included_files = None
                    except Exception:
                        included_files = None

                # Parse datetime from filename
                created_at = self._parse_backup_datetime(fn, path)

                backup_entry = {
                    "filename": fn,
                    "size": size,
                    "type": btype,
                    "includedFiles": included_files,
                    "hasUsers": "_with_users" in fn,
                    "createdAt": created_at.isoformat() if created_at else None,
                }
                sortable_backups.append((created_at or sort_floor, backup_entry))

        # Sort by real datetime descending (newest first).
        sortable_backups.sort(key=lambda item: item[0], reverse=True)
        backups = [entry for _, entry in sortable_backups]

        return Response({"backups": backups})

    @extend_schema(summary="Download backup file", responses={200: OpenApiTypes.BINARY, 404: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="download/(?P<filename>.+)")
    def download(self, request, filename=None):
        """Download backup file."""
        backups_dir = services.BACKUPS_DIR
        # Sanitize filename to prevent directory traversal
        safe_filename = os.path.basename(filename) if filename else None
        if not safe_filename:
            return Response({"error": "Invalid filename"}, status=400)
        path = os.path.join(backups_dir, safe_filename)
        if not os.path.exists(path):
            return Response({"error": "File not found"}, status=404)
        return FileResponse(open(path, "rb"), as_attachment=True, filename=safe_filename)

    @extend_schema(summary="Delete a backup file", responses={200: OpenApiTypes.OBJECT, 404: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["delete"], url_path="delete/(?P<filename>.+)")
    def delete_backup(self, request, filename=None):
        """Delete a single backup file."""
        backups_dir = services.BACKUPS_DIR
        safe_filename = os.path.basename(filename) if filename else None
        if not safe_filename:
            return Response({"ok": False, "error": "Invalid filename"}, status=400)
        path = os.path.join(backups_dir, safe_filename)
        if not os.path.exists(path):
            return Response({"ok": False, "error": "File not found"}, status=404)
        try:
            if os.path.isfile(path):
                os.unlink(path)
            elif os.path.isdir(path):
                shutil.rmtree(path)
            return Response({"ok": True, "deleted": safe_filename})
        except Exception as e:
            return Response({"ok": False, "error": str(e)}, status=500)

    @extend_schema(
        summary="Delete multiple backup files",
        request=inline_serializer(
            name="DeleteMultipleBackupsSerializer",
            fields={"filenames": serializers.ListField(child=serializers.CharField())},
        ),
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="delete-multiple")
    def delete_multiple(self, request):
        """Delete multiple backup files."""
        filenames = request.data.get("filenames", [])
        if not filenames:
            return Response({"ok": False, "error": "No filenames provided"}, status=400)

        backups_dir = services.BACKUPS_DIR
        deleted = []
        errors = []

        for filename in filenames:
            safe_filename = os.path.basename(filename)
            if not safe_filename:
                errors.append({"filename": filename, "error": "Invalid filename"})
                continue
            path = os.path.join(backups_dir, safe_filename)
            if not os.path.exists(path):
                errors.append({"filename": filename, "error": "File not found"})
                continue
            try:
                if os.path.isfile(path):
                    os.unlink(path)
                elif os.path.isdir(path):
                    shutil.rmtree(path)
                deleted.append(safe_filename)
            except Exception as e:
                errors.append({"filename": filename, "error": str(e)})

        return Response({"ok": True, "deleted": deleted, "errors": errors})

    @extend_schema(
        summary="Start backup process",
        parameters=[OpenApiParameter("include_users", OpenApiTypes.BOOL, location=OpenApiParameter.QUERY)],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="start")
    def start_backup(self, request):
        """Trigger SSE backup stream."""
        include_users = request.query_params.get("include_users", "0") == "1"

        def _sse_event(data: str):
            return f"data: {json.dumps({'message': data})}\n\n"

        def event_stream():
            yield _sse_event("Backup started")
            try:
                for msg in services.backup_all(include_users=include_users):
                    # Send comment as keepalive to prevent timeout
                    yield ": keepalive\n\n"
                    if msg.startswith("RESULT_PATH:"):
                        path = msg.split(":", 1)[1]
                        yield _sse_event(f"Backup finished: {path}")
                    else:
                        yield _sse_event(msg)
            except Exception as ex:
                yield _sse_event(f"Error: {str(ex)}")

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable buffering in Nginx
        return response

    @extend_schema(summary="Delete all backups", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["delete"], url_path="delete-all")
    def delete_all(self, request):
        """Purge all backups."""
        backups_dir = services.BACKUPS_DIR
        deleted = 0
        try:
            if os.path.exists(backups_dir):
                for fn in os.listdir(backups_dir):
                    path = os.path.join(backups_dir, fn)
                    try:
                        if os.path.isfile(path):
                            os.unlink(path)
                            deleted += 1
                        elif os.path.isdir(path):
                            shutil.rmtree(path)
                            deleted += 1
                    except Exception:
                        pass
            return Response({"ok": True, "deleted": deleted})
        except Exception as e:
            return Response({"ok": False, "error": str(e)}, status=500)

    @extend_schema(summary="Upload backup file", responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="upload")
    def upload(self, request):
        """Multi-part upload for existing archives."""
        if "backup_file" not in request.FILES:
            return Response({"ok": False, "error": "No file provided"}, status=400)

        uploaded_file = request.FILES["backup_file"]

        # Validate file extension
        if not (
            uploaded_file.name.endswith(".json")
            or uploaded_file.name.endswith(".json.gz")
            or uploaded_file.name.endswith(".gz")
            or uploaded_file.name.endswith(".tar.gz")
            or uploaded_file.name.endswith(".tgz")
            or uploaded_file.name.endswith(".tar.zst")
            or uploaded_file.name.endswith(".zst")
        ):
            return Response(
                {"ok": False, "error": "Invalid file type. Only .json, .gz, or .tar.zst files are allowed."}, status=400
            )

        # Save to backups directory
        backups_dir = services.BACKUPS_DIR
        os.makedirs(backups_dir, exist_ok=True)

        # Generate unique filename with timestamp if needed
        timestamp = timezone.localtime().strftime("%Y%m%d-%H%M%S")
        base_name = os.path.splitext(uploaded_file.name)[0]
        ext = uploaded_file.name[len(base_name) :]
        filename = f"uploaded-{timestamp}-{base_name}{ext}"

        file_path = os.path.join(backups_dir, filename)

        try:
            with open(file_path, "wb+") as destination:
                for chunk in uploaded_file.chunks():
                    destination.write(chunk)
            return Response({"ok": True, "filename": filename})
        except Exception as e:
            return Response({"ok": False, "error": str(e)}, status=500)

    @extend_schema(
        summary="Restore from backup",
        parameters=[
            OpenApiParameter("file", OpenApiTypes.STR, location=OpenApiParameter.QUERY),
            OpenApiParameter("include_users", OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="restore")
    def restore(self, request):
        """Trigger SSE restore stream."""
        filename = request.query_params.get("file")
        if not filename:
            return Response({"error": "Missing file parameter"}, status=400)

        gz_path = os.path.join(services.BACKUPS_DIR, filename)
        include_users = request.query_params.get("include_users", "0") == "1"

        def _sse_event(data: str):
            return f"data: {json.dumps({'message': data})}\n\n"

        def event_stream():
            yield _sse_event("Restore started")
            try:
                for msg in services.restore_from_file(gz_path, include_users=include_users):
                    # Send comment as keepalive to prevent timeout
                    yield ": keepalive\n\n"
                    if msg.startswith("PROGRESS:"):
                        progress = msg.split(":")[1]
                        yield f"data: {json.dumps({'progress': progress})}\n\n"
                    else:
                        yield _sse_event(msg)
                yield _sse_event("Restore finished")
            except Exception as ex:
                yield _sse_event(f"Error: {str(ex)}")

        response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
        response["Cache-Control"] = "no-cache"
        response["X-Accel-Buffering"] = "no"  # Disable buffering in Nginx
        return response


class ServerManagementViewSet(ApiErrorHandlingMixin, viewsets.ViewSet):
    serializer_class = ServerManagementPlaceholderSerializer
    permission_classes = [IsAuthenticated, IsSuperuserOrAdminGroup]

    @extend_schema(
        summary="Clear application cache",
        parameters=[
            OpenApiParameter(
                name="user_id",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Optional user ID for per-user cache clearing. If omitted, clears global cache.",
                required=False,
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="clear-cache")
    def clear_cache(self, request):
        """
        Clear application cache.

        Supports two modes:
        1. Global cache clear (default): Clears all cache entries
        2. Per-user cache clear: Increments user's cache version for O(1) invalidation

        Query Parameters:
            user_id (optional): User ID for per-user cache clearing
        """
        # Check for per-user cache clearing
        user_id = request.query_params.get("user_id")

        if user_id:
            # Per-user cache clearing via namespace version increment
            try:
                user_id = int(user_id)
                from cache.namespace import namespace_manager

                new_version = namespace_manager.increment_user_version(user_id)
                return Response(
                    {
                        "ok": True,
                        "message": f"Cache cleared for user {user_id}",
                        "user_id": user_id,
                        "new_version": new_version,
                    }
                )
            except ValueError:
                return Response({"ok": False, "message": "Invalid user_id parameter"}, status=400)
            except Exception as e:
                return Response({"ok": False, "message": f"Failed to clear user cache: {str(e)}"}, status=500)

        # Global cache clear (backward compatible)
        try:
            caches["default"].clear()
            _clear_cacheops_query_store()
            return Response(
                {
                    "ok": True,
                    "message": "Cache cleared",
                    "cleared_stores": ["default", "cacheops"],
                }
            )
        except Exception as e:
            logger.error("Failed to clear global caches: %s", e, exc_info=True)
            return Response({"ok": False, "message": str(e)}, status=500)

    @extend_schema(summary="Run live cache health check", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="cache-health")
    def cache_health(self, request):
        """Run a live cache round-trip and Redis connectivity probe."""
        try:
            return Response(services.get_cache_health_status())
        except Exception as e:
            logger.error("Failed to run cache health check: %s", e, exc_info=True)
            return Response(
                {
                    "ok": False,
                    "message": "Failed to run cache health check",
                    "errors": [str(e)],
                },
                status=500,
            )

    @extend_schema(summary="Run media files diagnostic", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="media-diagnostic")
    def media_diagnostic(self, request):
        """Comprehensive check of disk vs DB."""
        try:
            results = services.check_media_files()
            settings_info = {
                "mediaRoot": str(settings.MEDIA_ROOT),
                "mediaUrl": settings.MEDIA_URL,
                "debug": settings.DEBUG,
            }
            return Response({"ok": True, "results": results, "settings": settings_info})
        except Exception as e:
            return Response({"ok": False, "message": str(e)}, status=500)

    @extend_schema(summary="Repair media file paths", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="media-repair")
    def media_repair(self, request):
        """Automated path fixing."""
        try:
            repairs = services.repair_media_paths()
            return Response({"ok": True, "repairs": repairs})
        except Exception as e:
            return Response({"ok": False, "message": str(e)}, status=500)

    @extend_schema(summary="Get OpenRouter status and AI model usage", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["get"], url_path="openrouter-status")
    def openrouter_status(self, request):
        """Return OpenRouter credit status and AI model usage by feature."""
        usage_tracking_unavailable = False

        def _to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

        def _load_llm_models_config():
            llm_config_path = finders.find("llm_models.json")
            if not llm_config_path:
                llm_config_path = settings.BASE_DIR / "business_suite" / "static" / "llm_models.json"

            try:
                with open(llm_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                return {"providers": {}}

        def _empty_period_usage(now_dt: datetime.datetime, *, month: bool) -> dict:
            return {
                "requestCount": 0,
                "successCount": 0,
                "failedCount": 0,
                "totalTokens": 0,
                "totalCost": 0.0,
                "year": now_dt.year,
                "month": now_dt.month if month else None,
            }

        def _serialize_period_usage(aggregate: dict, now_dt: datetime.datetime, *, month: bool) -> dict:
            return {
                "requestCount": int(aggregate.get("request_count") or 0),
                "successCount": int(aggregate.get("success_count") or 0),
                "failedCount": int(aggregate.get("failed_count") or 0),
                "totalTokens": int(aggregate.get("total_tokens") or 0),
                "totalCost": float(aggregate.get("total_cost") or 0.0),
                "year": now_dt.year,
                "month": now_dt.month if month else None,
            }

        def _period_usage(
            feature_name: str | None,
            provider_name: str,
            now_dt: datetime.datetime,
            *,
            month: bool,
            model_name: str | None = None,
        ) -> dict:
            nonlocal usage_tracking_unavailable
            if usage_tracking_unavailable:
                return _empty_period_usage(now_dt, month=month)

            filters = {
                "provider": provider_name,
                "created_at__year": now_dt.year,
            }
            if feature_name is not None:
                filters["feature"] = feature_name
            if model_name is not None:
                filters["model"] = model_name
            if month:
                filters["created_at__month"] = now_dt.month

            try:
                aggregate = AIRequestUsage.objects.filter(**filters).aggregate(
                    request_count=Count("id"),
                    success_count=Count("id", filter=Q(success=True)),
                    failed_count=Count("id", filter=Q(success=False)),
                    total_tokens=Sum("total_tokens"),
                    total_cost=Sum("cost_usd"),
                )
            except (ProgrammingError, OperationalError):
                usage_tracking_unavailable = True
                return _empty_period_usage(now_dt, month=month)

            return _serialize_period_usage(aggregate, now_dt, month=month)

        def _model_breakdown(
            feature_name: str,
            provider_name: str,
            now_dt: datetime.datetime,
            *,
            month: bool,
        ) -> list[dict]:
            nonlocal usage_tracking_unavailable
            if usage_tracking_unavailable:
                return []

            filters = {
                "feature": feature_name,
                "provider": provider_name,
                "created_at__year": now_dt.year,
            }
            if month:
                filters["created_at__month"] = now_dt.month

            try:
                rows = (
                    AIRequestUsage.objects.filter(**filters)
                    .values("model")
                    .annotate(
                        request_count=Count("id"),
                        success_count=Count("id", filter=Q(success=True)),
                        failed_count=Count("id", filter=Q(success=False)),
                        total_tokens=Sum("total_tokens"),
                        total_cost=Sum("cost_usd"),
                    )
                    .order_by("-total_cost", "-request_count", "model")
                )
            except (ProgrammingError, OperationalError):
                usage_tracking_unavailable = True
                return []

            return [
                {
                    "model": row.get("model") or "unknown",
                    "requestCount": int(row.get("request_count") or 0),
                    "successCount": int(row.get("success_count") or 0),
                    "failedCount": int(row.get("failed_count") or 0),
                    "totalTokens": int(row.get("total_tokens") or 0),
                    "totalCost": float(row.get("total_cost") or 0.0),
                }
                for row in rows
            ]

        api_key = getattr(settings, "OPENROUTER_API_KEY", None)
        base_url = getattr(settings, "OPENROUTER_API_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
        timeout = float(getattr(settings, "OPENROUTER_HEALTHCHECK_TIMEOUT", 10.0))
        now = timezone.now()

        key_status = {
            "ok": False,
            "httpStatus": None,
            "message": "OPENROUTER_API_KEY is not configured.",
            "label": None,
            "limit": None,
            "limitRemaining": None,
            "limitReset": None,
            "usage": None,
            "usageDaily": None,
            "usageWeekly": None,
            "usageMonthly": None,
            "isFreeTier": None,
            "endpoint": f"{base_url}/key",
        }
        credits_status = {
            "ok": False,
            "available": False,
            "httpStatus": None,
            "message": "Management key required for /credits endpoint.",
            "totalCredits": None,
            "totalUsage": None,
            "remaining": None,
            "endpoint": f"{base_url}/credits",
        }

        if api_key:
            headers = {"Authorization": f"Bearer {api_key}", "Accept": "application/json"}

            try:
                key_resp = requests.get(key_status["endpoint"], headers=headers, timeout=timeout)
                key_status["httpStatus"] = key_resp.status_code
                if key_resp.status_code == 200:
                    payload = key_resp.json()
                    data = payload.get("data", {}) if isinstance(payload, dict) else {}
                    key_status.update(
                        {
                            "ok": True,
                            "message": None,
                            "label": data.get("label"),
                            "limit": _to_float(data.get("limit")),
                            "limitRemaining": _to_float(data.get("limit_remaining")),
                            "limitReset": data.get("limit_reset"),
                            "usage": _to_float(data.get("usage")),
                            "usageDaily": _to_float(data.get("usage_daily")),
                            "usageWeekly": _to_float(data.get("usage_weekly")),
                            "usageMonthly": _to_float(data.get("usage_monthly")),
                            "isFreeTier": data.get("is_free_tier"),
                        }
                    )
                else:
                    body_excerpt = (key_resp.text or "").replace("\n", " ").strip()[:200]
                    key_status["message"] = body_excerpt or f"HTTP {key_resp.status_code}"
            except requests.RequestException as exc:
                key_status["message"] = str(exc)
            except ValueError:
                key_status["message"] = "Invalid JSON response from /key endpoint."

            try:
                credits_resp = requests.get(credits_status["endpoint"], headers=headers, timeout=timeout)
                credits_status["httpStatus"] = credits_resp.status_code
                if credits_resp.status_code == 200:
                    payload = credits_resp.json()
                    data = payload.get("data", {}) if isinstance(payload, dict) else {}
                    total_credits = _to_float(data.get("total_credits"))
                    total_usage = _to_float(data.get("total_usage"))
                    remaining = None
                    if total_credits is not None and total_usage is not None:
                        remaining = total_credits - total_usage
                    credits_status.update(
                        {
                            "ok": True,
                            "available": True,
                            "message": None,
                            "totalCredits": total_credits,
                            "totalUsage": total_usage,
                            "remaining": remaining,
                        }
                    )
                elif credits_resp.status_code in (401, 403):
                    credits_status["message"] = "Management key required to read /credits."
                else:
                    body_excerpt = (credits_resp.text or "").replace("\n", " ").strip()[:200]
                    credits_status["message"] = body_excerpt or f"HTTP {credits_resp.status_code}"
            except requests.RequestException as exc:
                credits_status["message"] = str(exc)
            except ValueError:
                credits_status["message"] = "Invalid JSON response from /credits endpoint."

        llm_config = _load_llm_models_config()
        providers = llm_config.get("providers", {}) if isinstance(llm_config, dict) else {}
        current_provider = getattr(settings, "LLM_PROVIDER", "openrouter")
        default_model = getattr(settings, "LLM_DEFAULT_MODEL", "google/gemini-2.5-flash-lite")
        check_passport_model = getattr(settings, "CHECK_PASSPORT_MODEL", "") or default_model
        provider_info = providers.get(current_provider, {}) if isinstance(providers, dict) else {}
        available_models = provider_info.get("models", []) if isinstance(provider_info, dict) else []

        def _feature_usage_row(
            *,
            feature_name: str,
            purpose: str,
            model_strategy: str,
            effective_model: str,
        ) -> dict:
            return {
                "feature": feature_name,
                "purpose": purpose,
                "modelStrategy": model_strategy,
                "effectiveModel": effective_model,
                "provider": current_provider,
                "usageCurrentMonth": _period_usage(feature_name, current_provider, now, month=True),
                "usageCurrentYear": _period_usage(feature_name, current_provider, now, month=False),
                "modelBreakdownCurrentMonth": _model_breakdown(feature_name, current_provider, now, month=True),
                "modelBreakdownCurrentYear": _model_breakdown(feature_name, current_provider, now, month=False),
            }

        feature_rows = [
            _feature_usage_row(
                feature_name=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
                purpose="Extracts invoice/customer data from uploaded invoice files.",
                model_strategy="Uses request llm_model override, otherwise LLM_DEFAULT_MODEL.",
                effective_model=default_model,
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR,
                purpose="Extracts structured passport fields in hybrid MRZ + AI flow.",
                model_strategy="Uses LLM_DEFAULT_MODEL unless parser is explicitly instantiated with a model.",
                effective_model=default_model,
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
                purpose="Classifies uploaded documents into document types using vision AI.",
                model_strategy="Uses request model override, otherwise LLM_DEFAULT_MODEL.",
                effective_model=default_model,
            ),
        ]

        if check_passport_model != default_model:
            feature_rows.append(
                _feature_usage_row(
                    feature_name=AIUsageFeature.PASSPORT_CHECK_API,
                    purpose="Validates passport uploadability via async /customers/check-passport/ API.",
                    model_strategy="Uses CHECK_PASSPORT_MODEL from settings for AI decisions.",
                    effective_model=check_passport_model,
                )
            )

        ai_model_usage = {
            "provider": current_provider,
            "providerName": provider_info.get("name", current_provider),
            "defaultModel": default_model,
            "availableModels": available_models,
            "usageCurrentMonth": _period_usage(None, current_provider, now, month=True),
            "usageCurrentYear": _period_usage(None, current_provider, now, month=False),
            "features": feature_rows,
        }

        effective_credit_remaining = key_status.get("limitRemaining")
        effective_credit_source = "key.limit_remaining"
        if effective_credit_remaining is None and credits_status.get("remaining") is not None:
            effective_credit_remaining = credits_status["remaining"]
            effective_credit_source = "credits.total_credits-total_usage"

        return Response(
            {
                "ok": True,
                "openrouter": {
                    "configured": bool(api_key),
                    "baseUrl": base_url,
                    "checkedAt": datetime.datetime.now(datetime.timezone.utc).isoformat(),
                    "keyStatus": key_status,
                    "creditsStatus": credits_status,
                    "effectiveCreditRemaining": effective_credit_remaining,
                    "effectiveCreditSource": (
                        effective_credit_source if effective_credit_remaining is not None else None
                    ),
                },
                "aiModels": ai_model_usage,
            }
        )
