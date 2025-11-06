from django.urls import path

from . import views

app_name = "admin_tools"

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("backup/", views.backup_page, name="backup_page"),
    path("backup/start/", views.backup_stream, name="backup_start"),
    path("backups/<path:filename>", views.download_backup, name="download_backup"),
    path("restore/", views.restore_page, name="restore_page"),
    path("restore/start/", views.restore_stream, name="restore_start"),
    path("restore/upload/", views.upload_backup, name="upload_backup"),
    path("manage-server/", views.manage_server_page, name="manage_server"),
    path("manage-server/action/", views.manage_server_action, name="manage_server_action"),
]
