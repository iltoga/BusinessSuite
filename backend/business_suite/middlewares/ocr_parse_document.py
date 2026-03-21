from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from core.utils.passport_ocr import extract_mrz_data


class OcrParseDocumentMiddleware(MiddlewareMixin):
    def __call__(self, request):
        if request.method == "POST" and request.FILES:
            file = request.FILES.get("file", False)
            try:
                post_data = request.POST.copy()
                post_data["data"] = extract_mrz_data(file)
                request._post = post_data
            except FileNotFoundError:
                return JsonResponse({"error": "The specified file could not be found"})
            except Exception as e:
                return JsonResponse({"error": "An unexpected error occurred: " + str(e)})

        response = super().__call__(request)
        return response
