import json
import os

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
    backups_dir = os.path.join(settings.BASE_DIR, "backups")
    path = os.path.join(backups_dir, filename)
    if not os.path.exists(path):
        return HttpResponse("Not found", status=404)
    return FileResponse(open(path, "rb"), as_attachment=True, filename=filename)


@superuser_required
def backup_page(request):
    backups = []
    backups_dir = os.path.join(settings.BASE_DIR, "backups")
    if os.path.exists(backups_dir):
        for fn in sorted(os.listdir(backups_dir), reverse=True):
            backups.append(fn)
    return render(request, "admin_tools/backup_restore.html", {"backups": backups})


def _sse_event(data: str):
    return f"data: {json.dumps({'message': data})}\n\n"


@superuser_required
def backup_stream(request):
    """Start backup and stream progress via SSE."""

    def event_stream():
        events = []
        yield _sse_event("Backup started")

        include_users = request.GET.get("include_users", "0") == "1"
        try:
            # pass a callback that appends messages to events
            gz = services.backup_all(
                progress_callback=lambda m: events.append(_sse_event(m)), include_users=include_users
            )
            # send queued events
            for e in events:
                yield e
            yield _sse_event(f"Backup finished: {gz}")
        except Exception as ex:
            yield _sse_event(f"Error: {str(ex)}")

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


@superuser_required
def restore_page(request):
    backups_dir = os.path.join(settings.BASE_DIR, "backups")
    backups = []
    if os.path.exists(backups_dir):
        for fn in sorted(os.listdir(backups_dir), reverse=True):
            backups.append(fn)
    return render(request, "admin_tools/restore.html", {"backups": backups})


@superuser_required
def restore_stream(request):
    """Start restore from supplied `file` GET param and stream progress via SSE."""
    fn = request.GET.get("file")
    if not fn:
        return HttpResponse("Missing file parameter", status=400)
    gz_path = os.path.join(settings.BASE_DIR, "backups", fn)

    def event_stream():
        events = []
        yield _sse_event("Restore started")
        try:
            services.restore_from_file(gz_path, progress_callback=lambda m: events.append(_sse_event(m)))
            for e in events:
                yield e
            yield _sse_event("Restore finished")
        except Exception as ex:
            yield _sse_event(f"Error: {str(ex)}")

    return StreamingHttpResponse(event_stream(), content_type="text/event-stream")


@superuser_required
def manage_server_page(request):
    return render(request, "admin_tools/manage_server.html", {})


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
