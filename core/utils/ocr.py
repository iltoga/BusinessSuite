import os
import tempfile
from datetime import datetime

from django.core.files.uploadedfile import InMemoryUploadedFile
from passporteye import read_mrz
from pdf2image.pdf2image import convert_from_path


def extract_mrz_data(file) -> tuple[dict, dict]:
    converted_file_name = ""
    file_to_delete = ""
    file_name, file_ext = os.path.splitext(file.name)

    # Check if file is an instance of InMemoryUploadedFile
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
        file_path = file.path

    # Convert PDF to image
    content_type = ""
    file_ext = ""
    try:
        content_type = file.content_type
    except Exception:
        # try to extract extension from file name
        file_ext = os.path.splitext(file_path)[1]
    if content_type == "application/pdf" or file_ext == ".pdf":
        images = convert_from_path(file_path)
        if images:
            file_name, _ = os.path.splitext(file_path)
            converted_file_name = f"{file_name}.png"
            images[0].save(converted_file_name, "PNG")
        else:
            raise Exception("Failed to convert PDF to image")

    # Extract data from image
    # image_path: if converted_file_name exists, use it, otherwise use file_path
    image_path = converted_file_name if converted_file_name != "" and os.path.exists(converted_file_name) else file_path

    try:
        mrz = read_mrz(image_path)
        # remove temporary files if exist
        if converted_file_name != "" and os.path.exists(converted_file_name):
            os.remove(converted_file_name)
        if file_to_delete != "" and os.path.exists(file_to_delete):
            os.remove(file_to_delete)
        if mrz:
            mrz_data = mrz.to_dict()
            # validate MRZ data
            valid_number = mrz_data.get("valid_number", False)
            doc_number = mrz_data.get("number", False)
            if not valid_number or not doc_number:
                raise Exception("Could not extract document number from the file.")
            valid_expiration_date = mrz_data.get("valid_expiration_date", False)

            expiration_date_timestamp = mrz_data.get("expiration_date", False)
            expiration_date = None
            # parse expiration date into a datetime object
            if expiration_date_timestamp:
                try:
                    expiration_date = datetime.strptime(expiration_date_timestamp, "%y%m%d").date()
                except ValueError:
                    raise Exception("Could not extract expiration date from the file.")
            if not expiration_date:
                raise Exception("Could not extract expiration date from the file.")

            extracted_data = {"document_number": doc_number, "expiration_date": expiration_date}

            return (mrz.to_dict(), extracted_data)
        else:
            raise Exception(
                "Failed to scan document. Ensure that the document is a valid passport and the quality of the image or PDF is good"
            )
    except FileNotFoundError:
        raise Exception("The specified file could not be found")
    except Exception as e:
        raise Exception(str(e))
