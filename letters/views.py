import os

from django.conf import settings
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import FileResponse, HttpResponse, HttpResponseBadRequest, JsonResponse
from django.shortcuts import get_object_or_404
from django.utils.text import slugify
from django.views import View
from django.views.generic import FormView

from customers.models import Customer
from letters.forms import SuratPermohonanForm
from letters.services.LetterService import LetterService


class SuratPermohonanView(LoginRequiredMixin, FormView):
    template_name = "letters/surat_permohonan.html"
    form_class = SuratPermohonanForm

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        return context


class DownloadSuratPermohonanView(LoginRequiredMixin, View):
    form_fields = [
        "doc_date",
        "visa_type",
        "name",
        "gender",
        "country",
        "birth_place",
        "birthdate",
        "passport_no",
        "passport_exp_date",
        "address_bali",
    ]

    def post(self, request, *args, **kwargs):
        customer_id = request.POST.get("customer_id") or request.POST.get("customer")
        if not customer_id:
            msg = "Please select a customer before generating the letter."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": msg}, status=400)
            return HttpResponseBadRequest(msg)

        try:
            customer = get_object_or_404(Customer, pk=int(customer_id))
        except (TypeError, ValueError):
            msg = "Invalid customer selected."
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": msg}, status=400)
            return HttpResponseBadRequest(msg)

        extra_data = {field: (request.POST.get(field, "") or "") for field in self.form_fields}

        service = LetterService(customer, settings.DOCX_SURAT_PERMOHONAN_PERPANJANGAN_TEMPLATE_NAME)

        try:
            data = service.generate_letter_data(extra_data)
            buffer = service.generate_letter_document(data)
            safe_name = slugify(f"surat_permohonan_{customer.full_name}", allow_unicode=False).replace("-", "_")
            # Normalize filename: replace any remaining dots with underscores to avoid accidental extra dots
            safe_name = (safe_name or "surat_permohonan").replace(".", "_")
            filename = f"{safe_name}.docx"

            return FileResponse(
                buffer,
                as_attachment=True,
                filename=filename,
                content_type="application/vnd.openxmlformats-officedocument.wordprocessingml.document",
            )
        except FileNotFoundError as exc:
            msg = str(exc)
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": msg}, status=500)
            return HttpResponse(msg, status=500)
        except Exception as exc:  # pragma: no cover - handled generically
            msg = f"Unable to generate Surat Permohonan: {exc}"
            if request.headers.get("x-requested-with") == "XMLHttpRequest":
                return JsonResponse({"error": msg}, status=500)
            return HttpResponse(msg, status=500)
        finally:
            _cleanup_tmp_files(service.generated_temp_files)


def _cleanup_tmp_files(paths):
    for tmp_path in paths:
        try:
            if os.path.exists(tmp_path):
                os.remove(tmp_path)
        except OSError:
            continue
