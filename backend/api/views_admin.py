# Admin Tools API ViewSets
import ast
import datetime
import json
import logging
import os
import re
import shutil
import tarfile
from collections.abc import Mapping

import requests
from admin_tools import services
from admin_tools import tasks as admin_tasks
from api.permissions import (
    SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR,
    IsSuperuserOrAdminGroup,
    is_superuser_or_admin_group,
)
from api.serializers.local_resilience_serializer import LocalResilienceSettingsSerializer
from api.serializers.ui_settings_serializer import UiSettingsSerializer
from api.utils.redis_sse import iter_replay_and_live_events
from api.utils.sse_auth import sse_token_auth_required
from api.views import ApiErrorHandlingMixin
from core.models import AppSetting
from core.models.ai_request_usage import AIRequestUsage
from core.services.ai_runtime_settings_service import AI_RUNTIME_SETTING_DEFINITIONS, AIRuntimeSettingsService
from core.services.ai_usage_service import AIUsageFeature
from core.services.app_setting_service import AppSettingScope, AppSettingService
from core.services.local_resilience_service import LocalResilienceService
from core.services.redis_streams import format_sse_event, resolve_last_event_id, stream_user_key
from core.services.ui_settings_service import UiSettingsService
from django.conf import settings
from django.contrib.auth import get_user_model
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
from rest_framework.status import HTTP_400_BAD_REQUEST

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


def _build_sse_response(event_stream) -> StreamingHttpResponse:
    response = StreamingHttpResponse(event_stream, content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"
    return response


def _query_param(request, key: str, default: str | None = None) -> str | None:
    if hasattr(request, "query_params"):
        return request.query_params.get(key, default)
    return request.GET.get(key, default)


def _as_bool(value: str | None) -> bool:
    return str(value).strip().lower() in {"1", "true", "yes", "on"}


def _resolve_backup_path(filename: str | None) -> str | None:
    safe_filename = os.path.basename(filename or "")
    if not safe_filename:
        return None
    path = os.path.join(services.BACKUPS_DIR, safe_filename)
    return path if os.path.exists(path) else None


def _stream_admin_events(
    *,
    user_id: int,
    replay_cursor: str | None,
    start_new: bool,
    accepted_events: set[str],
    enqueue_callback,
):
    def event_stream():
        if start_new:
            try:
                enqueue_callback()
            except Exception as exc:
                yield format_sse_event(data={"message": f"Error: {exc}"})
                return

        for stream_event in iter_replay_and_live_events(
            stream_key=stream_user_key(user_id), last_event_id=replay_cursor
        ):
            if stream_event is None:
                yield ": keepalive\n\n"
                continue

            if stream_event.event not in accepted_events:
                continue

            payload = dict(stream_event.payload)
            terminal = bool(payload.pop("_terminal", False))
            yield format_sse_event(data=payload, event_id=stream_event.id)
            if terminal:
                break

    return _build_sse_response(event_stream())


# ============================================================================
# Plain Django views for SSE endpoints (bypass DRF content negotiation)
# ============================================================================


@sse_token_auth_required()
def backup_start_sse(request):
    """SSE endpoint for backup with replay support."""
    if not is_superuser_or_admin_group(request.user):
        return JsonResponse({"error": SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR}, status=403)

    include_users = _as_bool(_query_param(request, "include_users", "0"))
    replay_mode = _as_bool(_query_param(request, "replay", "0"))
    replay_cursor = resolve_last_event_id(request) if replay_mode else None
    return _stream_admin_events(
        user_id=request.user.id,
        replay_cursor=replay_cursor,
        start_new=not replay_mode,
        accepted_events={"backup_started", "backup_message", "backup_finished", "backup_failed"},
        enqueue_callback=lambda: admin_tasks.run_backup_stream.delay(
            user_id=request.user.id,
            include_users=include_users,
        ),
    )


@sse_token_auth_required()
def backup_restore_sse(request):
    """SSE endpoint for restore with replay support."""
    if not is_superuser_or_admin_group(request.user):
        return JsonResponse({"error": SUPERUSER_OR_ADMIN_PERMISSION_REQUIRED_ERROR}, status=403)

    gz_path = _resolve_backup_path(_query_param(request, "file"))
    if not gz_path:
        return JsonResponse({"error": "Missing file parameter"}, status=400)

    include_users = _as_bool(_query_param(request, "include_users", "0"))
    replay_mode = _as_bool(_query_param(request, "replay", "0"))
    replay_cursor = resolve_last_event_id(request) if replay_mode else None
    return _stream_admin_events(
        user_id=request.user.id,
        replay_cursor=replay_cursor,
        start_new=not replay_mode,
        accepted_events={
            "restore_started",
            "restore_progress",
            "restore_message",
            "restore_finished",
            "restore_failed",
        },
        enqueue_callback=lambda: admin_tasks.run_restore_stream.delay(
            user_id=request.user.id,
            archive_path=gz_path,
            include_users=include_users,
        ),
    )


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
        parameters=[
            OpenApiParameter("include_users", OpenApiTypes.BOOL, location=OpenApiParameter.QUERY),
            OpenApiParameter(
                "replay",
                OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Set true to replay existing stream events without enqueuing a new backup job.",
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="start")
    def start_backup(self, request):
        """Trigger stream-backed SSE backup execution."""
        include_users = _as_bool(_query_param(request, "include_users", "0"))
        replay_mode = _as_bool(_query_param(request, "replay", "0"))
        replay_cursor = resolve_last_event_id(request) if replay_mode else None
        return _stream_admin_events(
            user_id=request.user.id,
            replay_cursor=replay_cursor,
            start_new=not replay_mode,
            accepted_events={"backup_started", "backup_message", "backup_finished", "backup_failed"},
            enqueue_callback=lambda: admin_tasks.run_backup_stream.delay(
                user_id=request.user.id,
                include_users=include_users,
            ),
        )

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
            OpenApiParameter(
                "replay",
                OpenApiTypes.BOOL,
                location=OpenApiParameter.QUERY,
                description="Set true to replay existing stream events without enqueuing a new restore job.",
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["post"], url_path="restore")
    def restore(self, request):
        """Trigger stream-backed SSE restore execution."""
        gz_path = _resolve_backup_path(_query_param(request, "file"))
        if not gz_path:
            return Response({"error": "Missing file parameter"}, status=400)

        include_users = _as_bool(_query_param(request, "include_users", "0"))
        replay_mode = _as_bool(_query_param(request, "replay", "0"))
        replay_cursor = resolve_last_event_id(request) if replay_mode else None
        return _stream_admin_events(
            user_id=request.user.id,
            replay_cursor=replay_cursor,
            start_new=not replay_mode,
            accepted_events={
                "restore_started",
                "restore_progress",
                "restore_message",
                "restore_finished",
                "restore_failed",
            },
            enqueue_callback=lambda: admin_tasks.run_restore_stream.delay(
                user_id=request.user.id,
                archive_path=gz_path,
                include_users=include_users,
            ),
        )


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
            return Response(services.get_cache_health_status(user_id=request.user.id))
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

    @extend_schema(
        summary="Run calendar sync health check",
        parameters=[
            OpenApiParameter(
                name="stuck_after_minutes",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Pending sync threshold in minutes.",
                required=False,
            ),
            OpenApiParameter(
                name="sample_limit",
                type=OpenApiTypes.INT,
                location=OpenApiParameter.QUERY,
                description="Maximum number of stuck event samples returned.",
                required=False,
            ),
        ],
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get"], url_path="calendar-sync-health")
    def calendar_sync_health(self, request):
        """Report stuck pending application calendar sync events."""
        try:
            raw_stuck_after = request.query_params.get("stuck_after_minutes", "5")
            raw_sample_limit = request.query_params.get("sample_limit", "20")
            try:
                stuck_after_minutes = int(raw_stuck_after)
            except (TypeError, ValueError):
                return Response(
                    {
                        "ok": False,
                        "message": "Invalid stuck_after_minutes parameter",
                    },
                    status=400,
                )

            try:
                sample_limit = int(raw_sample_limit)
            except (TypeError, ValueError):
                return Response(
                    {
                        "ok": False,
                        "message": "Invalid sample_limit parameter",
                    },
                    status=400,
                )

            return Response(
                services.get_calendar_sync_health_status(
                    stuck_after_minutes=stuck_after_minutes,
                    sample_limit=sample_limit,
                )
            )
        except Exception as e:
            logger.error("Failed to run calendar sync health check: %s", e, exc_info=True)
            return Response(
                {
                    "ok": False,
                    "message": "Failed to run calendar sync health check",
                    "errors": [str(e)],
                },
                status=500,
            )

    @extend_schema(
        summary="Get or update local resilience settings",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get", "patch"], url_path="local-resilience")
    def local_resilience(self, request):
        settings_obj = LocalResilienceService.get_settings()

        if request.method.lower() == "get":
            return Response(LocalResilienceSettingsSerializer(settings_obj).data)

        raw_enabled = request.data.get("enabled")
        raw_desktop_mode = request.data.get("desktop_mode", request.data.get("desktopMode"))

        parsed_enabled = None
        if raw_enabled is not None:
            if isinstance(raw_enabled, bool):
                parsed_enabled = raw_enabled
            else:
                normalized = str(raw_enabled).strip().lower()
                if normalized in {"1", "true", "yes", "on"}:
                    parsed_enabled = True
                elif normalized in {"0", "false", "no", "off"}:
                    parsed_enabled = False
                else:
                    return Response({"detail": "Invalid 'enabled' value"}, status=HTTP_400_BAD_REQUEST)

        updated = LocalResilienceService.update_settings(
            enabled=parsed_enabled,
            desktop_mode=raw_desktop_mode,
            updated_by=request.user,
        )
        return Response(LocalResilienceSettingsSerializer(updated).data)

    @extend_schema(summary="Reset local media vault epoch", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="local-resilience/reset-vault")
    def reset_local_resilience_vault(self, request):
        settings_obj = LocalResilienceService.reset_vault_epoch(updated_by=request.user)
        return Response(
            {
                "ok": True,
                "message": "Local media vault reset requested. Desktop clients must re-bootstrap.",
                "vaultEpoch": settings_obj.vault_epoch,
            }
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

    @extend_schema(
        summary="Get or update global UI settings",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get", "patch"], url_path="ui-settings")
    def ui_settings(self, request):
        if request.method.lower() == "get":
            return Response(UiSettingsSerializer(UiSettingsService.get_settings()).data)

        raw_use_overlay_menu = request.data.get("use_overlay_menu", request.data.get("useOverlayMenu"))

        parsed_use_overlay_menu = None
        if raw_use_overlay_menu is not None:
            if isinstance(raw_use_overlay_menu, bool):
                parsed_use_overlay_menu = raw_use_overlay_menu
            else:
                normalized = str(raw_use_overlay_menu).strip().lower()
                if normalized in {"1", "true", "yes", "on"}:
                    parsed_use_overlay_menu = True
                elif normalized in {"0", "false", "no", "off"}:
                    parsed_use_overlay_menu = False
                else:
                    return Response({"detail": "Invalid 'useOverlayMenu' value"}, status=HTTP_400_BAD_REQUEST)

        updated = UiSettingsService.update_settings(
            use_overlay_menu=parsed_use_overlay_menu,
            updated_by=request.user,
        )
        return Response(UiSettingsSerializer(updated).data)

    @extend_schema(summary="Repair media file paths", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="media-repair")
    def media_repair(self, request):
        """Automated path fixing."""
        try:
            repairs = services.repair_media_paths()
            return Response({"ok": True, "repairs": repairs})
        except Exception as e:
            return Response({"ok": False, "message": str(e)}, status=500)

    @extend_schema(
        summary="List and create application settings",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get", "post"], url_path="app-settings")
    def app_settings(self, request):
        if request.method.lower() == "post":
            name = str(request.data.get("name") or "").strip().upper()
            if not name:
                return Response({"detail": "name is required."}, status=HTTP_400_BAD_REQUEST)
            value = request.data.get("value")
            scope = str(request.data.get("scope") or "").strip().lower()
            description = str(request.data.get("description") or "").strip()

            definition = AI_RUNTIME_SETTING_DEFINITIONS.get(name)
            effective_scope = scope or (definition.scope if definition else AppSettingScope.BACKEND)
            if effective_scope not in {AppSettingScope.BACKEND, AppSettingScope.FRONTEND, AppSettingScope.BOTH}:
                return Response({"detail": "scope must be backend, frontend, or both."}, status=HTTP_400_BAD_REQUEST)

            if value is None:
                return Response({"detail": "value is required."}, status=HTTP_400_BAD_REQUEST)

            if definition is not None:
                try:
                    AIRuntimeSettingsService.update_runtime_settings({name: value}, updated_by=request.user)
                except ValueError as exc:
                    return Response({"detail": str(exc)}, status=HTTP_400_BAD_REQUEST)
            else:
                AppSettingService.set_raw(
                    name=name,
                    value=str(value),
                    scope=effective_scope,
                    description=description,
                    updated_by=request.user,
                )

        defaults = AIRuntimeSettingsService.defaults()
        db_rows = AppSettingService._load_all_rows()
        known_names = sorted(set(defaults.keys()) | set(db_rows.keys()))
        items = []
        for name in known_names:
            definition = AI_RUNTIME_SETTING_DEFINITIONS.get(name)
            hardcoded_default = defaults.get(name)
            raw_effective = (
                AIRuntimeSettingsService.get(name)
                if definition is not None
                else AppSettingService.get_effective_raw(name, hardcoded_default)
            )
            items.append(
                AppSettingService.get_metadata(
                    name,
                    hardcoded_default=hardcoded_default,
                    fallback_scope=definition.scope if definition else AppSettingScope.BACKEND,
                    fallback_description=definition.description if definition else "",
                    effective_value=raw_effective,
                )
            )
        return Response({"items": items})

    @extend_schema(
        summary="Update or delete single application setting",
        parameters=[
            OpenApiParameter(
                name="name",
                type=OpenApiTypes.STR,
                location=OpenApiParameter.PATH,
                description="Case-insensitive application setting name.",
                required=True,
            ),
        ],
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["patch", "delete"], url_path=r"app-settings/(?P<name>[^/.]+)")
    def app_setting_item(self, request, name: str | None = None):
        setting_name = str(name or "").strip().upper()
        if not setting_name:
            return Response({"detail": "Invalid setting name."}, status=HTTP_400_BAD_REQUEST)

        if request.method.lower() == "delete":
            AppSettingService.delete_raw(setting_name)
            effective_value = (
                AIRuntimeSettingsService.get(setting_name)
                if setting_name in AI_RUNTIME_SETTING_DEFINITIONS
                else AppSettingService.get_effective_raw(setting_name, None)
            )
            definition = AI_RUNTIME_SETTING_DEFINITIONS.get(setting_name)
            metadata = AppSettingService.get_metadata(
                setting_name,
                hardcoded_default=AIRuntimeSettingsService.defaults().get(setting_name) if definition else None,
                fallback_scope=definition.scope if definition else AppSettingScope.BACKEND,
                fallback_description=definition.description if definition else "",
                effective_value=effective_value,
            )
            return Response({"ok": True, "name": setting_name, "effectiveValue": effective_value, "setting": metadata})

        payload = dict(request.data or {})
        if "value" in payload and payload["value"] is None:
            AppSettingService.delete_raw(setting_name)
            effective_value = (
                AIRuntimeSettingsService.get(setting_name)
                if setting_name in AI_RUNTIME_SETTING_DEFINITIONS
                else AppSettingService.get_effective_raw(setting_name, None)
            )
            definition = AI_RUNTIME_SETTING_DEFINITIONS.get(setting_name)
            metadata = AppSettingService.get_metadata(
                setting_name,
                hardcoded_default=AIRuntimeSettingsService.defaults().get(setting_name) if definition else None,
                fallback_scope=definition.scope if definition else AppSettingScope.BACKEND,
                fallback_description=definition.description if definition else "",
                effective_value=effective_value,
            )
            return Response({"ok": True, "name": setting_name, "effectiveValue": effective_value, "setting": metadata})

        current = AppSetting.objects.filter(name=setting_name).first()
        scope = str(payload.get("scope") or (current.scope if current else AppSettingScope.BACKEND)).strip().lower()
        description = str(
            payload.get("description")
            if payload.get("description") is not None
            else (current.description if current else "")
        ).strip()
        if scope not in {AppSettingScope.BACKEND, AppSettingScope.FRONTEND, AppSettingScope.BOTH}:
            return Response({"detail": "scope must be backend, frontend, or both."}, status=HTTP_400_BAD_REQUEST)

        if "value" not in payload:
            return Response({"detail": "value is required."}, status=HTTP_400_BAD_REQUEST)
        value = payload.get("value")
        definition = AI_RUNTIME_SETTING_DEFINITIONS.get(setting_name)
        if definition:
            try:
                AIRuntimeSettingsService.update_runtime_settings({setting_name: value}, updated_by=request.user)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=HTTP_400_BAD_REQUEST)
        else:
            AppSettingService.set_raw(
                name=setting_name,
                value=str(value),
                scope=scope,
                description=description or "",
                updated_by=request.user,
            )
        effective_value = (
            AIRuntimeSettingsService.get(setting_name)
            if definition
            else AppSettingService.get_effective_raw(setting_name, None)
        )
        metadata = AppSettingService.get_metadata(
            setting_name,
            hardcoded_default=AIRuntimeSettingsService.defaults().get(setting_name) if definition else None,
            fallback_scope=definition.scope if definition else AppSettingScope.BACKEND,
            fallback_description=definition.description if definition else "",
            effective_value=effective_value,
        )
        return Response({"ok": True, "name": setting_name, "effectiveValue": effective_value, "setting": metadata})

    @extend_schema(
        summary="Get or update OpenRouter status and AI model usage",
        request=OpenApiTypes.OBJECT,
        responses={200: OpenApiTypes.OBJECT, 400: OpenApiTypes.OBJECT},
    )
    @action(detail=False, methods=["get", "patch"], url_path="openrouter-status")
    def openrouter_status(self, request):
        """Return OpenRouter credit status and AI model usage by feature.

        PATCH accepts DB overrides for supported AI runtime setting names.
        """
        usage_tracking_unavailable = False

        if request.method.lower() == "patch":

            def _as_mapping(value):
                if isinstance(value, list) and len(value) == 1:
                    value = value[0]
                if isinstance(value, Mapping):
                    return dict(value)
                if isinstance(value, str):
                    try:
                        parsed = json.loads(value)
                    except ValueError:
                        try:
                            parsed = ast.literal_eval(value)
                        except (ValueError, SyntaxError):
                            return None
                    return parsed if isinstance(parsed, dict) else None
                return None

            payload = _as_mapping(request.data) or {}
            updates = _as_mapping(payload.get("settings"))
            if updates is None:
                updates = _as_mapping(payload.get("updates"))
            if updates is None:
                updates = {name: value for name, value in payload.items() if name not in {"settings", "updates"}}

            if not isinstance(updates, dict):
                return Response({"detail": "Invalid payload. Expected an object."}, status=HTTP_400_BAD_REQUEST)

            def _normalize_setting_name(raw_name):
                candidate = str(raw_name or "").strip()
                if not candidate:
                    return None
                if candidate in AI_RUNTIME_SETTING_DEFINITIONS:
                    return candidate
                uppercase = candidate.upper()
                if uppercase in AI_RUNTIME_SETTING_DEFINITIONS:
                    return uppercase
                snake_upper = re.sub(r"([a-z0-9])([A-Z])", r"\1_\2", candidate).replace("-", "_").upper()
                if snake_upper in AI_RUNTIME_SETTING_DEFINITIONS:
                    return snake_upper
                return None

            normalized_updates: dict[str, object] = {}
            for raw_name, raw_value in updates.items():
                normalized_name = _normalize_setting_name(raw_name)
                if normalized_name:
                    normalized_updates[normalized_name] = raw_value

            if not normalized_updates:
                bracket_updates: dict[str, object] = {}
                for raw_name, raw_value in updates.items():
                    key = str(raw_name)
                    if key.startswith("settings[") and key.endswith("]"):
                        bracket_updates[key[len("settings[") : -1]] = raw_value
                    elif key.startswith("updates[") and key.endswith("]"):
                        bracket_updates[key[len("updates[") : -1]] = raw_value
                for raw_name, raw_value in bracket_updates.items():
                    normalized_name = _normalize_setting_name(raw_name)
                    if normalized_name:
                        normalized_updates[normalized_name] = raw_value
            if not normalized_updates:
                return Response(
                    {"detail": "No supported runtime settings provided."},
                    status=HTTP_400_BAD_REQUEST,
                )

            try:
                AIRuntimeSettingsService.update_runtime_settings(normalized_updates, updated_by=request.user)
            except ValueError as exc:
                return Response({"detail": str(exc)}, status=HTTP_400_BAD_REQUEST)

        def _to_float(value):
            try:
                return float(value)
            except (TypeError, ValueError):
                return None

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
        base_url = str(
            AIRuntimeSettingsService.get("OPENROUTER_API_BASE_URL") or "https://openrouter.ai/api/v1"
        ).rstrip("/")
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

        runtime_settings = AIRuntimeSettingsService.get_many()
        runtime_settings_rows = AIRuntimeSettingsService.serialize_runtime_settings()
        workflow_bindings = AIRuntimeSettingsService.workflow_bindings()
        binding_by_feature = {item.get("feature"): item for item in workflow_bindings}

        model_catalog = AIRuntimeSettingsService.get_model_catalog()
        providers = model_catalog.get("providers", {}) if isinstance(model_catalog, dict) else {}
        provider_names = {"openrouter": "OpenRouter", "openai": "OpenAI", "groq": "Groq"}

        configured_provider = AIRuntimeSettingsService.get_llm_provider()
        current_provider = configured_provider if configured_provider in provider_names else "openrouter"

        global_default_model = AIRuntimeSettingsService.get_llm_default_model()
        openrouter_default_model = AIRuntimeSettingsService.get_openrouter_default_model()
        openai_default_model = AIRuntimeSettingsService.get_openai_default_model()
        groq_default_model = AIRuntimeSettingsService.get_groq_default_model()

        document_categorizer_model = AIRuntimeSettingsService.get_document_categorizer_model()
        document_categorizer_model_high = AIRuntimeSettingsService.get_document_categorizer_model_high()
        document_validator_model = AIRuntimeSettingsService.get_document_validator_model()
        check_passport_model = AIRuntimeSettingsService.get_check_passport_model()
        document_ocr_structured_model = AIRuntimeSettingsService.get_document_ocr_structured_model()
        invoice_import_model = AIRuntimeSettingsService.get_invoice_import_model()
        passport_ocr_model = AIRuntimeSettingsService.get_passport_ocr_model()

        provider_info = providers.get(current_provider, {}) if isinstance(providers, dict) else {}
        available_models = provider_info.get("models", []) if isinstance(provider_info, dict) else []

        provider_availability = {
            "openrouter": bool(getattr(settings, "OPENROUTER_API_KEY", None)),
            "openai": bool(getattr(settings, "OPENAI_API_KEY", None)),
            "groq": bool(getattr(settings, "GROQ_API_KEY", None)),
        }

        router_enabled = AIRuntimeSettingsService.get_auto_fallback_enabled()
        fallback_candidates = AIRuntimeSettingsService.get_fallback_provider_order()
        fallback_model_candidates = AIRuntimeSettingsService.get_fallback_model_order()
        fallback_sticky_seconds = AIRuntimeSettingsService.get_fallback_sticky_seconds()

        def _provider_info(provider_key: str) -> dict:
            if not isinstance(providers, dict):
                return {}
            raw = providers.get(provider_key)
            return raw if isinstance(raw, dict) else {}

        def _provider_display_name(provider_key: str) -> str:
            info = _provider_info(provider_key)
            return str(info.get("name") or provider_names.get(provider_key, provider_key))

        def _configured_fallback_order_for(primary_provider: str) -> list[str]:
            configured: list[str] = []
            for candidate in fallback_candidates:
                if candidate not in provider_names:
                    continue
                if candidate in configured:
                    continue
                configured.append(candidate)
            return configured

        def _effective_fallback_order_for(primary_provider: str) -> list[str]:
            configured = _configured_fallback_order_for(primary_provider)
            return [provider for provider in configured if router_enabled and provider_availability.get(provider)]

        configured_fallback_order = _configured_fallback_order_for(current_provider)
        effective_fallback_order = _effective_fallback_order_for(current_provider)

        def _provider_default_model(provider_key: str) -> str:
            if provider_key == "openrouter":
                if current_provider == "openrouter":
                    configured_default_model = global_default_model or openrouter_default_model
                else:
                    configured_default_model = openrouter_default_model
                return configured_default_model or "google/gemini-3-flash-preview"
            if provider_key == "openai":
                if current_provider == "openai":
                    return global_default_model or openai_default_model or "gpt-5-mini"
                else:
                    return openai_default_model or "gpt-5-mini"
            if provider_key == "groq":
                return groq_default_model or "meta-llama/llama-4-scout-17b-16e-instruct"
            return global_default_model or "google/gemini-3-flash-preview"

        def _configured_fallback_model_order_for(primary_provider: str) -> list[dict]:
            configured: list[dict] = []
            seen: set[tuple[str, str]] = set()
            for model in fallback_model_candidates:
                model_id = str(model).strip()
                if not model_id:
                    continue
                provider_key = AIRuntimeSettingsService.get_provider_for_model(model_id, fallback=primary_provider)
                if not provider_key:
                    continue
                route = (provider_key, model_id)
                if route in seen:
                    continue
                seen.add(route)
                configured.append(
                    {
                        "provider": provider_key,
                        "providerName": _provider_display_name(provider_key),
                        "model": model_id,
                    }
                )

            if configured:
                return configured

            for provider in _configured_fallback_order_for(primary_provider):
                model_id = _provider_default_model(provider)
                route = (provider, model_id)
                if not model_id or route in seen:
                    continue
                seen.add(route)
                configured.append(
                    {
                        "provider": provider,
                        "providerName": _provider_display_name(provider),
                        "model": model_id,
                    }
                )
            return configured

        def _effective_fallback_model_order_for(primary_provider: str) -> list[dict]:
            configured = _configured_fallback_model_order_for(primary_provider)
            return [row for row in configured if router_enabled and provider_availability.get(row.get("provider"))]

        configured_fallback_model_order = _configured_fallback_model_order_for(current_provider)
        effective_fallback_model_order = _effective_fallback_model_order_for(current_provider)

        def _feature_primary_provider(model_override: str | None) -> str:
            return (
                AIRuntimeSettingsService.get_provider_for_model(model_override, fallback=current_provider)
                or current_provider
            )

        def _feature_primary_model(*, model_override: str | None, primary_provider: str) -> str:
            return (model_override or "").strip() or _provider_default_model(primary_provider)

        def _feature_failover_providers(*, primary_provider: str) -> list[dict]:
            entries: list[dict] = []
            configured_order = _configured_fallback_order_for(primary_provider)
            effective_order = set(_effective_fallback_order_for(primary_provider))
            for provider in configured_order:
                available = bool(provider_availability.get(provider))
                entries.append(
                    {
                        "provider": provider,
                        "providerName": _provider_display_name(provider),
                        "model": _provider_default_model(provider),
                        "available": available,
                        "active": provider in effective_order,
                    }
                )
            return entries

        def _feature_usage_row(
            *,
            feature_name: str,
            purpose: str,
            model_strategy: str,
            model_override: str | None = None,
            model_failover: str | None = None,
            model_failover_strategy: str | None = None,
        ) -> dict:
            binding = binding_by_feature.get(feature_name, {})
            feature_provider = _feature_primary_provider(model_override)
            feature_provider_info = _provider_info(feature_provider)
            primary_model = _feature_primary_model(
                model_override=model_override,
                primary_provider=feature_provider,
            )
            normalized_failover_model = (model_failover or "").strip()
            has_model_failover = bool(normalized_failover_model and normalized_failover_model != primary_model)
            return {
                "feature": feature_name,
                "purpose": purpose,
                "modelStrategy": model_strategy,
                "effectiveModel": primary_model,
                "provider": feature_provider,
                "providerName": str(
                    feature_provider_info.get("name", provider_names.get(feature_provider, feature_provider))
                ),
                "primaryProvider": feature_provider,
                "primaryProviderName": str(
                    feature_provider_info.get("name", provider_names.get(feature_provider, feature_provider))
                ),
                "primaryModel": primary_model,
                "providerSettingName": binding.get("providerSettingName"),
                "modelSettingName": binding.get("modelSettingName"),
                "modelFailoverSettingName": binding.get("modelFailoverSettingName"),
                "failoverProviders": _feature_failover_providers(primary_provider=feature_provider),
                "modelFailover": {
                    "enabled": has_model_failover,
                    "model": normalized_failover_model if has_model_failover else None,
                    "strategy": model_failover_strategy if has_model_failover else None,
                },
                "usageCurrentMonth": _period_usage(feature_name, feature_provider, now, month=True),
                "usageCurrentYear": _period_usage(feature_name, feature_provider, now, month=False),
                "modelBreakdownCurrentMonth": _model_breakdown(feature_name, feature_provider, now, month=True),
                "modelBreakdownCurrentYear": _model_breakdown(feature_name, feature_provider, now, month=False),
            }

        feature_rows = [
            _feature_usage_row(
                feature_name=AIUsageFeature.INVOICE_IMPORT_AI_PARSER,
                purpose="Extracts invoice/customer data from uploaded invoice files.",
                model_strategy="Uses INVOICE_IMPORT_MODEL (or request llm_model override) for this workflow.",
                model_override=invoice_import_model,
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.PASSPORT_OCR_AI_EXTRACTOR,
                purpose="Extracts structured passport fields in hybrid MRZ + AI flow.",
                model_strategy="Uses PASSPORT_OCR_MODEL (or parser model override) for this workflow.",
                model_override=passport_ocr_model,
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.DOCUMENT_AI_CATEGORIZER,
                purpose="Classifies uploaded documents into document types using vision AI.",
                model_strategy="Uses DOCUMENT_CATEGORIZER_MODEL (or request override) as pass-1 model.",
                model_override=document_categorizer_model,
                model_failover=document_categorizer_model_high,
                model_failover_strategy=("When pass 1 has no match, retries with DOCUMENT_CATEGORIZER_MODEL_HIGH."),
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.DOCUMENT_AI_VALIDATOR,
                purpose="Validates document quality/requirements with prompt-based AI rules.",
                model_strategy="Uses DOCUMENT_VALIDATOR_MODEL unless request override is provided.",
                model_override=document_validator_model,
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.DOCUMENT_OCR_AI_EXTRACTOR,
                purpose="Extracts typed structured fields from classified document images/PDFs.",
                model_strategy=(
                    "Uses DOCUMENT_OCR_STRUCTURED_MODEL, otherwise DOCUMENT_VALIDATOR_MODEL, "
                    "then provider default model."
                ),
                model_override=document_ocr_structured_model,
            ),
            _feature_usage_row(
                feature_name=AIUsageFeature.PASSPORT_CHECK_API,
                purpose="Validates passport uploadability via async /customers/check-passport/ API.",
                model_strategy="Uses CHECK_PASSPORT_MODEL for AI decisions.",
                model_override=check_passport_model,
            ),
        ]

        ai_model_usage = {
            "provider": current_provider,
            "providerName": provider_info.get("name", provider_names.get(current_provider, current_provider)),
            "defaultModel": _provider_default_model(current_provider),
            "availableModels": available_models,
            "runtimeSettings": runtime_settings_rows,
            "settingsMap": runtime_settings,
            "workflowBindings": workflow_bindings,
            "modelCatalog": model_catalog,
            "failover": {
                "enabled": router_enabled,
                "configuredProviderOrder": configured_fallback_order,
                "effectiveProviderOrder": effective_fallback_order,
                "configuredModelOrder": configured_fallback_model_order,
                "effectiveModelOrder": effective_fallback_model_order,
                "stickySeconds": fallback_sticky_seconds,
                "providers": [
                    {
                        "provider": provider,
                        "providerName": provider_names.get(provider, provider),
                        "defaultModel": _provider_default_model(provider),
                        "available": bool(provider_availability.get(provider)),
                        "active": provider in effective_fallback_order,
                    }
                    for provider in configured_fallback_order
                ],
            },
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
