import json
import os
import shutil

from django.conf import settings
from django.contrib.auth.decorators import user_passes_test
from django.core.cache import caches
from django.http import FileResponse, HttpResponse, JsonResponse, StreamingHttpResponse
from django.shortcuts import redirect, render
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_POST

from . import services


def superuser_required(view_func):
    return user_passes_test(lambda u: u.is_superuser)(view_func)


@superuser_required
def dashboard(request):
    return redirect("admin_tools:backup_page")


@superuser_required
def download_backup(request, filename):
    backups_dir = services.BACKUPS_DIR
    path = os.path.join(backups_dir, filename)
    if not os.path.exists(path):
        return HttpResponse("Not found", status=404)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=filename)


@superuser_required
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
                "tar.gz"
                if fn.endswith(".tar.gz") or fn.endswith(".tgz")
                else ("json.gz" if fn.endswith(".gz") else "json")
            )
            included_files = None
            if btype == "tar.gz":
                try:
                    import json as _json
                    import tarfile

                    with tarfile.open(path, "r:gz") as tar:
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


@superuser_required
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


@superuser_required
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


@superuser_required
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
                "tar.gz"
                if fn.endswith(".tar.gz") or fn.endswith(".tgz")
                else ("json.gz" if fn.endswith(".gz") else "json")
            )
            included_files = None
            if btype == "tar.gz":
                try:
                    import json as _json
                    import tarfile

                    with tarfile.open(path, "r:gz") as tar:
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


@superuser_required
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
                "tar.gz"
                if fn.endswith(".tar.gz") or fn.endswith(".tgz")
                else ("json.gz" if fn.endswith(".gz") else "json")
            )
            included_files = None
            if btype == "tar.gz":
                try:
                    import json as _json
                    import tarfile

                    with tarfile.open(path, "r:gz") as tar:
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


@superuser_required
def restore_stream(request):
    """Start restore from supplied `file` GET param and stream progress via SSE."""
    fn = request.GET.get("file")
    if not fn:
        return HttpResponse("Missing file parameter", status=400)
    gz_path = os.path.join(settings.BASE_DIR, "backups", fn)

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


@superuser_required
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
    ):
        return JsonResponse(
            {"ok": False, "error": "Invalid file type. Only .json or .json.gz files are allowed."}, status=400
        )

    # Save to backups directory
    backups_dir = services.BACKUPS_DIR
    os.makedirs(backups_dir, exist_ok=True)

    # Generate unique filename with timestamp if needed
    import datetime

    timestamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
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
@csrf_exempt
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

    if action == "restart_server":
        import signal
        import subprocess

        restart_cmd = os.getenv("SERVER_RESTART_CMD")
        try:
            if restart_cmd:
                os.system(restart_cmd)
                return JsonResponse({"ok": True, "message": f"Restart command executed: {restart_cmd}"})

            # Try to find Gunicorn master process and send SIGHUP
            try:
                ps = subprocess.check_output(["ps", "aux"]).decode()
                gunicorn_lines = [l for l in ps.splitlines() if "gunicorn" in l and "master" in l and "python" in l]
                if gunicorn_lines:
                    # Get the PID (second column)
                    pid = int(gunicorn_lines[0].split()[1])
                    os.kill(pid, signal.SIGHUP)
                    return JsonResponse({"ok": True, "message": f"Sent SIGHUP to Gunicorn master process (PID {pid})"})
            except Exception as e:
                # If ps or kill fails, continue to fallback
                pass

            # fallback: touch wsgi.py to trigger reload in many deployments
            wsgi_path = os.path.join(settings.BASE_DIR, "business_suite", "wsgi.py")
            if os.path.exists(wsgi_path):
                os.utime(wsgi_path, None)
                return JsonResponse({"ok": True, "message": "Touched wsgi.py to trigger reload"})
            # fallback: touch manage.py (may work in some setups)
            manage_path = os.path.join(settings.BASE_DIR, "manage.py")
            if os.path.exists(manage_path):
                os.utime(manage_path, None)
                return JsonResponse({"ok": True, "message": "Touched manage.py to trigger reload (fallback)"})
            return JsonResponse(
                {
                    "ok": False,
                    "message": (
                        "Could not find Gunicorn master process. "
                        "Set the SERVER_RESTART_CMD environment variable to a shell command that restarts your server, "
                        "or ensure business_suite/wsgi.py or manage.py exists and is writable to allow reload via file touch."
                    ),
                },
                status=500,
            )
        except Exception as e:
            return JsonResponse({"ok": False, "message": str(e)}, status=500)

    return JsonResponse({"error": "unknown action"}, status=400)
