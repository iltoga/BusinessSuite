from django.urls import path

from .views import DownloadSuratPermohonanView, SuratPermohonanView

app_name = "letters"

urlpatterns = [
    path("surat-permohonan/", SuratPermohonanView.as_view(), name="surat_permohonan"),
    path("surat-permohonan/download/", DownloadSuratPermohonanView.as_view(), name="download_surat_permohonan"),
]
