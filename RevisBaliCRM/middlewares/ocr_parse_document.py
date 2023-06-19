from django.http import JsonResponse
from django.utils.deprecation import MiddlewareMixin

from core.utils.passport_ocr import extract_mrz_data


class OcrParseDocumentMiddleware(MiddlewareMixin):
    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == "POST" and request.FILES:
            file = request.FILES.get("file", False)
            try:
                request.POST["data"] = extract_mrz_data(file)
            except FileNotFoundError:
                return JsonResponse({"error": "The specified file could not be found"})
            except Exception as e:
                return JsonResponse({"error": "An unexpected error occurred: " + str(e)})

        response = self.get_response(request)
        return response
