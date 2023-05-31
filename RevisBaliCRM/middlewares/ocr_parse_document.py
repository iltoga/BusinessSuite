import os
from django.utils.deprecation import MiddlewareMixin
import tempfile
from pdf2image import convert_from_path
from passporteye import read_mrz, mrz
from django.http import JsonResponse
from django.core.files.uploadedfile import InMemoryUploadedFile

class OcrParseDocumentMiddleware(MiddlewareMixin):

    def __init__(self, get_response):
        self.get_response = get_response

    def __call__(self, request):
        if request.method == 'POST' and request.FILES:
            file = request.FILES.get('file', False)
            file_name, file_ext = os.path.splitext(file.name)
            if file and file.name != '' and file.content_type != '' and file.size > 0:
                converted_file_name = ''
                if isinstance(file, InMemoryUploadedFile):
                    # If the file is in memory, create a temporary file and write the contents of the uploaded file to it
                    temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=file_ext)
                    for chunk in file.chunks():
                        temp_file.write(chunk)
                    temp_file.close()
                    file_path = temp_file.name
                    file_to_delete = file_path
                else:
                    # If the file is not in memory, it's already a temporary file on disk
                    file_path = file.temporary_file_path()

                if file.content_type == 'application/pdf':
                    images = convert_from_path(file_path)
                    if images:
                        converted_file_name = f'{file_name}.png'
                        images[0].save(converted_file_name, 'PNG')
                    else:
                        return JsonResponse({"error": "Failed to convert PDF to image"})

                # Extract data from image
                # image_path: if converted_file_name exists, use it, otherwise use file.name
                image_path = converted_file_name if converted_file_name != '' and os.path.exists(converted_file_name) else file_path
                try:
                    mrz = read_mrz(image_path)
                    # remove temporary files if exist
                    if converted_file_name != '' and os.path.exists(converted_file_name):
                        os.remove(converted_file_name)
                    if file_to_delete != '' and os.path.exists(file_to_delete):
                        os.remove(file_to_delete)
                    if mrz:
                        mrz_data = mrz.to_dict()
                        request.POST._mutable = True
                        request.POST['metadata'] = mrz_data
                        request.POST._mutable = False
                    else:
                        return JsonResponse({"error": "Failed to read MRZ"})
                except FileNotFoundError:
                    return JsonResponse({"error": "The specified file could not be found"})
                except Exception as e:
                    return JsonResponse({"error": "An unexpected error occurred: " + str(e)})

        response = self.get_response(request)
        return response
