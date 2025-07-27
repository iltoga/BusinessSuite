import os
import tempfile
from datetime import datetime

import pytesseract
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.utils import timezone
from passporteye import read_mrz

from core.utils.check_country import check_country_by_code
from core.utils.imgutils import convert_and_resize_image

pytesseract.pytesseract.tesseract_cmd = settings.TESSERACT_CMD

MRZ_FORMAT = {
    "mrz_type": "TD3",
    "type": "P",
    "country": "D",
    "number": "DE4YH2K78",
    "check_number": "8",
    "date_of_birth": "640812",
    "check_date_of_birth": "5",
    "expiration_date": "270228",
    "check_expiration_date": "3",
    "nationality": "D",
    "sex": "M",
    "names": "HANS",
    "surname": "SCHMIDT",
}


def extract_mrz_data(file, check_expiration=True, expiration_days=180) -> dict:
    converted_file_name = ""
    file_to_delete = ""
    file_name, file_ext = os.path.splitext(file.name)

    # Check if file is an instance of InMemoryUploadedFile
    # Check if file is an instance of InMemoryUploadedFile or TemporaryUploadedFile
    if isinstance(file, (InMemoryUploadedFile, TemporaryUploadedFile)):
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
        file_name, _ = os.path.splitext(file_path)
        converted_file_name = f"{file_name}.png"
        try:
            img, _ = convert_and_resize_image(file_path, content_type, return_encoded=False, resize=False)
            img.save(converted_file_name)
        except Exception as e:
            # delete temporary file
            try:
                if file_to_delete:
                    os.unlink(file_to_delete)
            except Exception:
                pass
            raise Exception(f"Failed to convert PDF to image: {e}")

    # Extract data from image
    # image_path: if converted_file_name exists, use it, otherwise use file_path
    image_path = converted_file_name if converted_file_name != "" and os.path.exists(converted_file_name) else file_path

    def extract_and_format_dates(parsed_mrz):
        for key in ["date_of_birth", "expiration_date"]:
            if key in parsed_mrz:
                dt = datetime.strptime(parsed_mrz[key], "%y%m%d").date()
                parsed_mrz[f"{key}_yyyy_mm_dd"] = dt.strftime("%Y-%m-%d")
        return parsed_mrz

    try:
        mrz_data = unit_extraction(image_path, MRZ_FORMAT)
        # delete temporary file
        if file_to_delete:
            os.unlink(file_to_delete)
        parsed_mrz = parse_mrz(mrz_data, MRZ_FORMAT)

        # Check the country code and nationality with fallback mechanism
        import logging

        logger = logging.getLogger("passport_ocr")

        # Try to map nationality first, then fallback to country
        nationality_code = parsed_mrz.get("nationality")
        country_code = parsed_mrz.get("country")

        closest_code = None
        final_country_code = None

        # Try nationality first
        if nationality_code:
            try:
                closest_code = check_country_by_code(nationality_code)
                final_country_code = nationality_code
                logger.debug(f"Successfully mapped nationality '{nationality_code}' to {closest_code.country}")
            except ValueError as e:
                logger.warning(f"Failed to map nationality '{nationality_code}': {e}")

        # Fallback to country if nationality failed
        if not closest_code and country_code:
            try:
                closest_code = check_country_by_code(country_code)
                final_country_code = country_code
                logger.debug(f"Successfully mapped country '{country_code}' to {closest_code.country}")
            except ValueError as e:
                logger.warning(f"Failed to map country '{country_code}': {e}")

        # If we found a valid country mapping, update the parsed_mrz
        if closest_code and final_country_code:
            parsed_mrz["country"] = final_country_code
            parsed_mrz["country_name"] = closest_code.country
            parsed_mrz["nationality"] = closest_code.alpha3_code  # Set nationality to the corrected code
            parsed_mrz["nationality_raw"] = nationality_code  # Keep the original OCR value for reference
            if closest_code.alpha3_code != final_country_code:
                parsed_mrz["country_closest_code"] = closest_code.alpha3_code
        else:
            logger.error(
                f"Cannot recognize nationality from uploaded file. Nationality: '{nationality_code}', Country: '{country_code}'"
            )
            # Don't raise an exception, just leave the fields as extracted

        # Check expiration date
        if check_expiration:
            if "expiration_date" in parsed_mrz:
                dt = datetime.strptime(parsed_mrz["expiration_date"], "%y%m%d").date()
                if dt < datetime.now().date():
                    raise Exception("Passport has expired")
                elif dt < datetime.now().date() + timezone.timedelta(days=expiration_days):
                    raise Exception(f"Passport is expiring in less than 6 months: {dt.strftime('%d/%m/%Y') }")

        if not check_mrz_all_info(parsed_mrz):
            raise Exception(
                "Failed to scan document. Ensure that the document is a valid passport and the quality of the image or PDF is good"
            )

        try:
            parsed_mrz = extract_and_format_dates(parsed_mrz)
        except ValueError as ve:
            raise ValueError(f"Could not extract date from the file: {ve}")

        # Success
        return parsed_mrz
    except FileNotFoundError:
        try:
            if file_to_delete:
                os.unlink(file_to_delete)
        except Exception:
            pass
        raise Exception("The specified file could not be found")
    except Exception as e:
        # delete temporary file
        try:
            if file_to_delete:
                os.unlink(file_to_delete)
        except Exception:
            pass
        # if e is "mrz_type" or e is "mrz_format" translate the error to a more user friendly message
        if e.args[0] == "mrz_type" or e.args[0] == "mrz_format":
            raise Exception("The specified file is not a valid passport")
        raise Exception(str(e))


def unit_extraction(image_path, mrz_format):
    """
    This function implements Passporteye read_mrz() function to extract identity information
    from the MRZ of an identity document.

    Input parameters:
    - image_folder: path to the folder containing the image of the identity document
    - image_sample: name of the image of the identity document containing information to extract
    - mrz_format: format of an MRZ

    Return:
    - mrz_data: dictionary containing identity information extacted
    """

    # Process image
    import logging

    logger = logging.getLogger("passport_ocr")
    mrz = read_mrz(image_path)
    logger.debug(f"read_mrz result: {mrz}")
    if mrz:
        mrz_dict = mrz.to_dict()
        logger.debug(f"Extracted MRZ dict: {mrz_dict}")
        mrz_data = filter_mrz(mrz_dict, mrz_format)
        logger.debug(f"Filtered MRZ data: {mrz_data}")
    else:
        logger.warning(f"No MRZ found in image: {image_path}")
        mrz_data = {}

    if mrz_data is None:
        logger.warning("MRZ data is None after filtering.")
        mrz_data = {}

    return mrz_data


def mrz_improver(mrz_list, mrz_format):
    """
    This function implements the Maximum likelihod of character algorithm to extract identity information
    from the MRZ of an identity document.

    Input parameters:
    - mrz_list: list containing a set of MRZ dictionary.
    - mrz_format: format of an MRZ

    Return:
    - mrz: improved extraction of identity information according to Maximum likelihood of characters
            algorithm
    """
    mrz = {}
    for key in mrz_format.keys():
        info_sample_len = []
        info_sample = []
        for i in range(len(mrz_list)):
            info_sample_len.append(len(mrz_list[i][key]))
            info_sample.append(mrz_list[i][key])

        while "" in info_sample:
            info_sample.remove("")

        # if key == 'surname':
        # print(info_sample)

        info_maximized = ""
        text_lenght = max(info_sample_len)

        for i in range(text_lenght):
            character_list = []
            for j in range(len(info_sample)):
                try:
                    character_list.append(info_sample[j][i])
                except:
                    character_list.append("<")

            max_occ = max(character_list, key=character_list.count)
            info_maximized = info_maximized + max_occ
        mrz[key] = info_maximized

    return mrz


def parse_mrz(mrz, mrz_format):
    """
    This function parse each field of an MRZ dictionary to improve the quality of identity
    information stored in it.

    Input parameters:
    - mrz: MRZ dictionary.
    - mrz_format: format of an MRZ

    Return:
    - mrz: improved MRZ dictionary
    """
    mrz_parsed = {}
    for key in mrz_format.keys():
        if key == "surname" or key == "name" or key == "names":
            mrz_parsed[key] = mrz[key].split(" K ")[0]
            # First letter capitalized and other letters in lower case.
            # if there are multiple names, they are separated by a space and
            # every name has the first letter capitalized and other letters in lower case.
            mrz_parsed[key] = " ".join([name.capitalize() for name in mrz_parsed[key].split(" ")])
        else:
            mrz_parsed[key] = mrz[key]

        mrz_parsed[key] = mrz_parsed[key].split("  ")[0]
        mrz_parsed[key] = mrz_parsed[key].replace("<", "")

    return mrz_parsed


def check_mrz_info(mrz_value, mrz_check_value):
    """
    This function implement the verification rule for check-digits of a MRZ

    Input parameters:
    mrz_value: information to check
    mrz_check_value: value of the check-digit to obtain after computation of the rule on 'mrz_value'

    Return: True or False
    """
    info = str(mrz_value)
    checker = 0
    alpha_to_num = {c: 10 + i for i, c in enumerate("ABCDEFGHIJKLMNOPQRSTUVWXYZ")}
    for i, c in enumerate(info):
        if i % 3 == 0:
            weight = 7
        elif i % 3 == 1:
            weight = 3
        else:
            weight = 1

        if c == "<":
            val = 0
        elif c.isalpha():
            val = alpha_to_num[c]
        else:
            val = int(c)

        checker += val * weight

    return str(checker % 10) == str(mrz_check_value)


def check_mrz_all_info(mrz):
    """
    This function implement check-digit verification for date_of_birth, expiration_date,
    sex, name and surname of an MRZ dictionary.

    Input parameter: MRZ dictionary

    Return: True or False
    """
    result = True
    # if not check_mrz_info(mrz["number"], mrz["check_number"]):
    # result = False

    if not check_mrz_info(mrz["date_of_birth"], mrz["check_date_of_birth"]):
        result = False

    if not check_mrz_info(mrz["expiration_date"], mrz["check_expiration_date"]):
        result = False

    if mrz["sex"] != "M" and mrz["sex"] != "F":
        result = False

    if "KKK" in mrz["names"] or "KKK" in mrz["surname"]:
        result = False

    return result


def dataset_size(mrz, actual_mrz):
    """
    This function determines the adjusted dataset size

    Input parameters:
    - MRZ dictionary
    - mrz_format: Actual identity information information into the identity document. Its format is
                described below
    Example:
    valid_mrz  = {
                    "mrz_type": "TD3",
                    "type": "P",
                    "country": "CMR",
                    "number": "01312168",
                    "check_number": "4",
                    "date_of_birth": "830408",
                    "check_date_of_birth": "1",
                    "expiration_date": "140611",
                    "check_expiration_date": "5",
                    "nationality": "CMR",
                    "sex": "M",
                    "names": "ADAMOU",
                    "surname": "NCHANGE KOUOTOU"
                }

    Return:
    - count: adjusted dataset size
    """
    count1 = 0
    for key in mrz.keys():
        count1 += len(mrz[key])

    count2 = 0
    for key in mrz.keys():
        count2 += len(actual_mrz[key])

    count = max(count1, count2)
    return count


def count_inaccuracy(extracted_mrz, actual_mrz):
    """
    This count the number of discrepency of characters between two MRZ dictionaries
    Return:
    - true_negative: number of discrepency of characters
    """
    true_negative = 0
    for key in actual_mrz.keys():
        if extracted_mrz[key] == actual_mrz[key]:
            true_negative += 0
        else:
            size = max([len(extracted_mrz[key]), len(actual_mrz[key])])
            for i in range(size):
                try:
                    if extracted_mrz[key][i] != actual_mrz[key][i]:
                        true_negative += 1
                except:
                    true_negative += 1

    return true_negative


def filter_mrz(extracted_mrz, actual_mrz):
    """
    This function remove unused field from a MRZ dictionary.

    Input parameters:
    - extracted_mrz : MRZ dictionary that contain unused field
    - actual_mrz : MRZ dictionary format that serve as benchmark for unused field removal

    Return:
    - mrz: extracted_mrz with unused field removed.
    """
    mrz = {}
    for key in actual_mrz.keys():
        mrz[key] = extracted_mrz[key]
    return mrz
