# Admin Tools API ViewSets
import datetime
import functools
import json
import os
import shutil
import tarfile

from django.conf import settings
from django.contrib.auth import get_user_model
from django.http import FileResponse, JsonResponse, StreamingHttpResponse
from drf_spectacular.types import OpenApiTypes
from drf_spectacular.utils import OpenApiParameter, extend_schema, inline_serializer
from rest_framework import permissions, serializers, viewsets
from rest_framework.decorators import action
from rest_framework.permissions import IsAuthenticated
from rest_framework.response import Response

from admin_tools import services
from api.views import ApiErrorHandlingMixin

User = get_user_model()


def is_superuser(user):
    return user.is_superuser


class IsSuperuser(permissions.BasePermission):
    """Permission class that allows only superusers."""

    def has_permission(self, request, view):
        return request.user and request.user.is_superuser


def sse_token_auth_required(view_func):
    """
    Decorator for SSE endpoints that need token auth.
    EventSource cannot send Authorization headers, so we accept token via query param.
    Supports both JWT tokens (rest_framework_simplejwt) and DRF Token auth.
    Falls back to session auth if no token provided.
    """

    @functools.wraps(view_func)
    def wrapper(request, *args, **kwargs):
        # Check for token in query param first (for EventSource)
        token_str = request.GET.get("token")
        if token_str:
            # Try JWT token first (starts with eyJ for base64-encoded JSON)
            if token_str.startswith("eyJ"):
                try:
                    from rest_framework_simplejwt.tokens import AccessToken

                    access_token = AccessToken(token_str)
                    user_id = access_token.get("user_id")
                    user = User.objects.get(pk=user_id)
                    if user.is_active and user.is_superuser:
                        request.user = user
                        return view_func(request, *args, **kwargs)
                    else:
                        return JsonResponse({"error": "Unauthorized"}, status=403)
                except Exception:
                    return JsonResponse({"error": "Invalid JWT token"}, status=401)
            else:
                # Try DRF Token auth
                try:
                    from rest_framework.authtoken.models import Token

                    token = Token.objects.select_related("user").get(key=token_str)
                    if token.user.is_active and token.user.is_superuser:
                        request.user = token.user
                        return view_func(request, *args, **kwargs)
                    else:
                        return JsonResponse({"error": "Unauthorized"}, status=403)
                except Exception:
                    return JsonResponse({"error": "Invalid token"}, status=401)

        # Fall back to session auth
        if request.user.is_authenticated and request.user.is_superuser:
            return view_func(request, *args, **kwargs)

        return JsonResponse({"error": "Authentication required"}, status=401)

    return wrapper


# ============================================================================
# Plain Django views for SSE endpoints (bypass DRF content negotiation)
# ============================================================================


@sse_token_auth_required
def backup_start_sse(request):
    """SSE endpoint for backup - bypasses DRF content negotiation."""
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


@sse_token_auth_required
def backup_restore_sse(request):
    """SSE endpoint for restore - bypasses DRF content negotiation."""
    filename = request.GET.get("file")
    if not filename:
        return JsonResponse({"error": "Missing file parameter"}, status=400)

    gz_path = os.path.join(settings.BASE_DIR, "backups", filename)
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
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated, IsSuperuser]

    def _parse_backup_datetime(self, filename: str) -> datetime.datetime | None:
        """Parse datetime from backup filename like backup-20260131-045527.tar.zst
        Returns timezone-aware UTC datetime since backup service uses utcnow().
        """
        import re

        # Match patterns like: backup-YYYYMMDD-HHMMSS or uploaded-YYYYMMDD-HHMMSS
        match = re.search(r"(\d{8})-(\d{6})", filename)
        if match:
            date_str = match.group(1)
            time_str = match.group(2)
            try:
                naive_dt = datetime.datetime.strptime(f"{date_str}{time_str}", "%Y%m%d%H%M%S")
                # Make timezone-aware (UTC) since backup filenames use utcnow()
                return naive_dt.replace(tzinfo=datetime.timezone.utc)
            except ValueError:
                pass
        return None

    @extend_schema(summary="List available backups", responses={200: OpenApiTypes.OBJECT})
    def list(self, request):
        """List local backups with metadata."""
        backups = []
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
                created_at = self._parse_backup_datetime(fn)

                backups.append(
                    {
                        "filename": fn,
                        "size": size,
                        "type": btype,
                        "includedFiles": included_files,
                        "hasUsers": "_with_users" in fn,
                        "createdAt": created_at.isoformat() if created_at else None,
                    }
                )

        # Sort by createdAt descending (newest first)
        backups.sort(key=lambda x: x["createdAt"] or "", reverse=True)

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
        timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
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

        gz_path = os.path.join(settings.BASE_DIR, "backups", filename)
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
    serializer_class = serializers.Serializer
    permission_classes = [IsAuthenticated, IsSuperuser]

    @extend_schema(summary="Clear application cache", responses={200: OpenApiTypes.OBJECT})
    @action(detail=False, methods=["post"], url_path="clear-cache")
    def clear_cache(self, request):
        """Global cache purge."""
        from django.core.cache import caches

        try:
            caches["default"].clear()
            return Response({"ok": True, "message": "Cache cleared"})
        except Exception as e:
            return Response({"ok": False, "message": str(e)}, status=500)

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
