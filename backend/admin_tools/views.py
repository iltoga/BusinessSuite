import json
import os
import shutil

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import caches
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from . import services


def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_superuser)(view_func)


def backup_access_required(view_func):
    return user_passes_test(
        lambda u: u.is_authenticated
        and (u.is_superuser or getattr(settings, "ADMIN_TOOLS_ALLOW_AUTHENTICATED_BACKUP_ACCESS", False))
    )(view_func)


@backup_access_required
def dashboard(request):
    return redirect("admin_tools:backup_page")


@backup_access_required
def download_backup(request, filename):
    backups_dir = services.BACKUPS_DIR
    path = os.path.join(backups_dir, filename)
    if not os.path.exists(path):
        return HttpResponse("Not found", status=404)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=filename)


@backup_access_required
def backup_page(request):
    backups = []
    backups_dir = services.BACKUPS_DIR
    if os.path.exists(backups_dir):
        for fn in sorted(os.listdir(backups_dir), reverse=True):
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
                    import json as _json
                    import tarfile

                    comp = "zst" if btype == "tar.zst" else "gz"
                    with tarfile.open(path, f"r:{comp}") as tar:
                        try:
                            member = tar.getmember("manifest.json")
                            f = tar.extractfile(member)
                            if f:
                                manifest = _json.load(f)
                                included_files = manifest.get("included_files_count")
                        except KeyError:
                            included_files = None
                except Exception:
                    included_files = None
            backups.append({"filename": fn, "size": size, "type": btype, "included_files": included_files})
    return render(request, "admin_tools/backup_restore.html", {"backups": backups})


def _sse_event(data: str):
    return f"data: {json.dumps({'message': data})}\n\n"


@backup_access_required
def backup_stream(request):
    """Start backup and stream progress via SSE."""

    def event_stream():
        yield _sse_event("Backup started")

        include_users = request.GET.get("include_users", "0") == "1"
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


@backup_access_required
@require_POST
def delete_backups(request):
    """Delete all files in the backups directory and return a JSON summary."""
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
                        # remove directories
                        shutil.rmtree(path)
                        deleted += 1
                except Exception:
                    # ignore removal errors, continue
                    pass
        return JsonResponse({"ok": True, "deleted": deleted})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@backup_access_required
def restore_page(request):
    backups_dir = services.BACKUPS_DIR
    backups = []
    if os.path.exists(backups_dir):
        for fn in sorted(os.listdir(backups_dir), reverse=True):
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
                    import json as _json
                    import tarfile

                    comp = "zst" if btype == "tar.zst" else "gz"
                    with tarfile.open(path, f"r:{comp}") as tar:
                        try:
                            member = tar.getmember("manifest.json")
                            f = tar.extractfile(member)
                            if f:
                                manifest = _json.load(f)
                                included_files = manifest.get("included_files_count")
                        except KeyError:
                            included_files = None
                except Exception:
                    included_files = None
            backups.append({"filename": fn, "size": size, "type": btype, "included_files": included_files})
    return render(request, "admin_tools/restore.html", {"backups": backups})


@backup_access_required
def backups_json(request):
    """Return a JSON list of available backups (name/size/type/included_files)."""
    backups = []
    backups_dir = services.BACKUPS_DIR
    if os.path.exists(backups_dir):
        for fn in sorted(os.listdir(backups_dir), reverse=True):
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
                    import json as _json
                    import tarfile

                    comp = "zst" if btype == "tar.zst" else "gz"
                    with tarfile.open(path, f"r:{comp}") as tar:
                        try:
                            member = tar.getmember("manifest.json")
                            f = tar.extractfile(member)
                            if f:
                                manifest = _json.load(f)
                                included_files = manifest.get("included_files_count")
                        except KeyError:
                            included_files = None
                except Exception:
                    included_files = None
            backups.append({"filename": fn, "size": size, "type": btype, "included_files": included_files})
    return JsonResponse({"backups": backups})


@backup_access_required
def restore_stream(request):
    """Start restore from supplied `file` GET param and stream progress via SSE."""
    fn = request.GET.get("file")
    if not fn:
        return HttpResponse("Missing file parameter", status=400)
    gz_path = os.path.join(services.BACKUPS_DIR, fn)

    def event_stream():
        yield _sse_event("Restore started")
        include_users = request.GET.get("include_users", "0") == "1"
        try:
            for msg in services.restore_from_file(gz_path, include_users=include_users):
                # Send comment as keepalive to prevent timeout
                yield ": keepalive\n\n"
                if msg.startswith("PROGRESS:"):
                    yield f"data: {json.dumps({'progress': msg.split(':')[1]})}\n\n"
                else:
                    yield _sse_event(msg)
            yield _sse_event("Restore finished")
        except Exception as ex:
            yield _sse_event(f"Error: {str(ex)}")

    response = StreamingHttpResponse(event_stream(), content_type="text/event-stream")
    response["Cache-Control"] = "no-cache"
    response["X-Accel-Buffering"] = "no"  # Disable buffering in Nginx
    return response


@backup_access_required
@require_POST
def upload_backup(request):
    """Handle backup file upload"""
    if "backup_file" not in request.FILES:
        return JsonResponse({"ok": False, "error": "No file provided"}, status=400)

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
        return JsonResponse(
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

    # Write the uploaded file
    try:
        with open(file_path, "wb+") as destination:
            for chunk in uploaded_file.chunks():
                destination.write(chunk)
        return JsonResponse({"ok": True, "filename": filename})
    except Exception as e:
        return JsonResponse({"ok": False, "error": str(e)}, status=500)


@superuser_required
def manage_server_page(request):
    return render(request, "admin_tools/manage_server.html", {})


@superuser_required
def document_types_page(request):
    return render(request, "admin_tools/document_types.html", {})


@superuser_required
@require_POST
def manage_server_action(request):
    """Perform server actions: clear_cache, restart_server"""
    action = request.POST.get("action")
    if not action:
        return JsonResponse({"error": "missing action"}, status=400)

    if action == "clear_cache":
        # clear default cache
        try:
            caches["default"].clear()
            return JsonResponse({"ok": True, "message": "Cache cleared"})
        except Exception as e:
            return JsonResponse({"ok": False, "message": str(e)}, status=500)

    if action == "media_diagnostic":
        try:
            results = services.check_media_files()
            settings_info = {
                "MEDIA_ROOT": str(settings.MEDIA_ROOT),
                "MEDIA_URL": settings.MEDIA_URL,
                "DEBUG": settings.DEBUG,
            }
            return JsonResponse({"ok": True, "results": results, "settings": settings_info})
        except Exception as e:
            return JsonResponse({"ok": False, "message": str(e)}, status=500)

    if action == "media_repair":
        try:
            repairs = services.repair_media_paths()
            return JsonResponse({"ok": True, "repairs": repairs})
        except Exception as e:
            return JsonResponse({"ok": False, "message": str(e)}, status=500)

    return JsonResponse({"error": "unknown action"}, status=400)
