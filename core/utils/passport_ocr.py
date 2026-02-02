import json
import logging
import os
import re
import tempfile
from datetime import datetime
from typing import List, Optional, Tuple

import numpy as np
import pytesseract
from django.conf import settings
from django.core.files.uploadedfile import InMemoryUploadedFile, TemporaryUploadedFile
from django.utils import timezone
from passporteye import read_mrz
from PIL import Image, ImageFilter, ImageOps, ImageStat
from skimage import filters

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
    logger = logging.getLogger("passport_ocr")
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
            # Use high DPI (300) for maximum quality MRZ extraction
            img, _ = convert_and_resize_image(file_path, content_type, return_encoded=False, resize=False, dpi=300)
            # Save with lossless compression to preserve quality for PassportEye/Tesseract
            img.save(converted_file_name, format="PNG", compress_level=1, optimize=False)
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

    quality_info = _assess_image_quality(image_path)
    if quality_info:
        logger.debug(
            "Passport image quality - width: %s height: %s contrast: %.2f brightness: %.2f",
            quality_info["width"],
            quality_info["height"],
            quality_info["contrast"],
            quality_info["brightness"],
        )
        if quality_info["width"] < 600 or quality_info["height"] < 600:
            logger.warning("Uploaded passport image is quite small; OCR accuracy may degrade.")

    def extract_and_format_dates(parsed_mrz):
        for key in ["date_of_birth", "expiration_date"]:
            if key in parsed_mrz:
                dt = datetime.strptime(parsed_mrz[key], "%y%m%d").date()
                # MRZ uses 2-digit years. Apply century correction:
                # - For date_of_birth: if parsed year > current year, assume 1900s
                # - For expiration_date: if parsed year < current year - 10, assume 2000s
                current_year = datetime.now().year
                if key == "date_of_birth":
                    # Birth dates in the future are invalid - assume 1900s
                    if dt.year > current_year:
                        dt = dt.replace(year=dt.year - 100)
                elif key == "expiration_date":
                    # Expiration dates more than 10 years in the past are likely 2000s
                    if dt.year < current_year - 10:
                        dt = dt.replace(year=dt.year + 100)
                parsed_mrz[f"{key}_yyyy_mm_dd"] = dt.strftime("%Y-%m-%d")
        return parsed_mrz

    try:
        preprocessed_variants, temp_variants = _build_preprocessed_variants(image_path)
        try:
            parsed_mrz = _run_mrz_pipeline(preprocessed_variants, logger)
        finally:
            for variant in temp_variants:
                try:
                    os.unlink(variant)
                except OSError:
                    logger.debug("Failed to remove temporary preprocessing file %s", variant)
        # delete temporary files created during processing
        for tmp_path in (file_to_delete, converted_file_name):
            if tmp_path and os.path.exists(tmp_path):
                try:
                    os.unlink(tmp_path)
                except OSError:
                    logger.debug("Failed to remove temporary file %s", tmp_path)

        # Check the country code and nationality with fallback mechanism
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
            for tmp_path in (file_to_delete, converted_file_name):
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception:
            pass
        raise Exception("The specified file could not be found")
    except Exception as e:
        # delete temporary file
        try:
            for tmp_path in (file_to_delete, converted_file_name):
                if tmp_path and os.path.exists(tmp_path):
                    os.unlink(tmp_path)
        except Exception:
            pass
        # if e is "mrz_type" or e is "mrz_format" translate the error to a more user friendly message
        if e.args[0] == "mrz_type" or e.args[0] == "mrz_format":
            raise Exception("The specified file is not a valid passport")
        raise Exception(str(e))


def unit_extraction(image_path, mrz_format, attempt_label="original"):
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
    logger = logging.getLogger("passport_ocr")
    mrz = read_mrz(image_path)
    logger.debug("[%s] read_mrz result: %s", attempt_label, mrz)
    if mrz:
        mrz_dict = mrz.to_dict()
        logger.debug("[%s] Extracted MRZ dict: %s", attempt_label, mrz_dict)
        mrz_data = filter_mrz(mrz_dict, mrz_format)
        logger.debug("[%s] Filtered MRZ data: %s", attempt_label, mrz_data)
    else:
        logger.warning("No MRZ found in image using %s", attempt_label)
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


def _is_mrz_obviously_corrupted(parsed_mrz: dict) -> bool:
    """Check if MRZ data is obviously corrupted (garbage OCR)."""
    # Check for excessive repeated characters (KKKKKK, EEEEEE, etc.)
    for key in ["names", "surname"]:
        value = str(parsed_mrz.get(key, ""))
        if len(value) > 5:
            # Check for 4+ consecutive identical characters
            for i in range(len(value) - 3):
                if value[i] == value[i + 1] == value[i + 2] == value[i + 3]:
                    return True

    # Check sex field (must be M or F, not A or other garbage)
    sex = parsed_mrz.get("sex", "")
    if sex and sex not in ["M", "F"]:
        return True

    # Check if country/nationality codes look like garbage (not 3 letters)
    for key in ["country", "nationality"]:
        code = str(parsed_mrz.get(key, ""))
        if code and (len(code) != 3 or not code.isalpha()):
            return True

    return False


def _run_mrz_pipeline(candidate_images: List[Tuple[str, str]], logger: logging.Logger) -> dict:
    """Try multiple preprocessed images until a valid MRZ passes validation."""

    best_candidate = None
    best_score = -1
    attempt_log = []

    for attempt_label, candidate_path in candidate_images:
        try:
            mrz_data = unit_extraction(candidate_path, MRZ_FORMAT, attempt_label=attempt_label)
        except Exception as extraction_error:  # pragma: no cover - defensive log
            logger.warning("%s attempt failed with error: %s", attempt_label, extraction_error)
            continue

        if not mrz_data:
            attempt_log.append(f"{attempt_label}: empty result")
            continue

        try:
            parsed_candidate = parse_mrz(mrz_data, MRZ_FORMAT)
        except KeyError as key_error:
            logger.debug("%s attempt missing field: %s", attempt_label, key_error)
            attempt_log.append(f"{attempt_label}: missing {key_error}")
            continue

        try:
            if check_mrz_all_info(parsed_candidate):
                logger.info("Passport MRZ successfully extracted via %s preprocessing", attempt_label)
                return parsed_candidate
            else:
                attempt_log.append(f"{attempt_label}: checksum mismatch")
        except KeyError as key_error:
            logger.debug("%s attempt raised KeyError during validation: %s", attempt_label, key_error)
            attempt_log.append(f"{attempt_label}: validation key {key_error}")
            continue

        candidate_score = dataset_size(parsed_candidate, MRZ_FORMAT)
        if candidate_score > best_score:
            best_candidate = parsed_candidate
            best_score = candidate_score

    if best_candidate:
        # Final sanity check: reject obviously corrupted MRZ data
        if _is_mrz_obviously_corrupted(best_candidate):
            logger.error(
                "Best-effort MRZ data is obviously corrupted (garbage characters, invalid codes). " "Attempts: %s",
                "; ".join(attempt_log),
            )
            raise Exception(
                "Failed to scan document. Ensure that the document is a valid passport and the quality of the image or PDF is good"
            )

        logger.warning(
            "Returning best-effort MRZ despite validation failure. Attempts: %s",
            "; ".join(attempt_log),
        )
        return best_candidate

    raise Exception(
        "Failed to scan document. Ensure that the document is a valid passport and the quality of the image or PDF is good"
    )


def _build_preprocessed_variants(image_path: str) -> Tuple[List[Tuple[str, str]], List[str]]:
    """Create additional preprocessed images to increase OCR robustness."""

    candidate_images: List[Tuple[str, str]] = [("original", image_path)]
    temp_files: List[str] = []

    try:
        with Image.open(image_path) as original_image:
            working_image = original_image.convert("RGB")
            working_image.load()
    except Exception:
        return candidate_images, temp_files

    variant_specs = [
        ("deskewed", _deskew_image(working_image)),
        (
            "contrast_boost",
            _apply_threshold(_ensure_min_width(working_image, target_width=1500), use_sauvola=False, autocontrast=True),
        ),
        (
            "binary_sauvola",
            _apply_threshold(_ensure_min_width(working_image, target_width=1800), use_sauvola=True, autocontrast=True),
        ),
        (
            "sharpened",
            _apply_sharpen(_ensure_min_width(working_image, target_width=1400)),
        ),
    ]

    for label, pil_image in variant_specs:
        if pil_image is None:
            continue
        temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".png")
        pil_image.save(temp_file.name, format="PNG")
        temp_file.close()
        temp_files.append(temp_file.name)
        candidate_images.append((label, temp_file.name))

    return candidate_images, temp_files


def _ensure_min_width(image: Image.Image, target_width: int) -> Image.Image:
    if image.width >= target_width:
        return image.copy()
    ratio = target_width / float(image.width)
    new_height = int(image.height * ratio)
    try:
        resample = Image.Resampling.LANCZOS
    except AttributeError:  # Pillow < 10
        resample = Image.LANCZOS
    return image.resize((target_width, new_height), resample)


def _deskew_image(image: Image.Image) -> Image.Image:
    try:
        osd = pytesseract.image_to_osd(image)
        rotation_match = re.search(r"Rotate: (\d+)", osd)
        if rotation_match:
            angle = int(rotation_match.group(1))
            if angle != 0:
                return image.rotate(-angle, expand=True)
    except pytesseract.TesseractError:
        pass
    return image.copy()


def _apply_threshold(
    image: Image.Image,
    *,
    use_sauvola: bool,
    autocontrast: bool,
) -> Image.Image:
    gray = image.convert("L")
    if autocontrast:
        gray = ImageOps.autocontrast(gray)
    np_image = np.array(gray)
    try:
        if use_sauvola:
            thresh = filters.threshold_sauvola(np_image, window_size=25)
        else:
            thresh = filters.threshold_otsu(np_image)
        binary = (np_image > thresh).astype(np.uint8) * 255
    except ValueError:
        binary = np_image
    pil_img = Image.fromarray(binary)
    return pil_img


def _apply_sharpen(image: Image.Image) -> Image.Image:
    return image.convert("L").filter(ImageFilter.UnsharpMask(radius=2, percent=175, threshold=3))


def _assess_image_quality(image_path: str):
    try:
        with Image.open(image_path) as img:
            gray = img.convert("L")
            stat = ImageStat.Stat(gray)
            return {
                "width": img.width,
                "height": img.height,
                "brightness": stat.mean[0],
                "contrast": stat.stddev[0],
            }
    except Exception:
        return None


def extract_passport_with_ai(file, use_ai: bool = True) -> dict:
    """
    Extract passport data using hybrid MRZ + AI vision approach.

    This function:
    1. Runs MRZ extraction using PassportEye/Tesseract (current logic)
    2. If use_ai is True, runs AI vision extraction to get additional fields
    3. Merges the results, with AI providing additional data and comparison logic

    Args:
        file: Uploaded file (InMemoryUploadedFile, TemporaryUploadedFile, or file-like object)
        use_ai: Whether to use AI extraction (default: True)

    Returns:
        dict: Combined passport data with fields from both MRZ and AI extraction.
              If AI extraction fails, includes 'ai_error' field with error message.
    """
    logger = logging.getLogger("passport_ocr")

    # Step 1: Run MRZ extraction first (this validates the document)
    # We call the original extract_mrz_data but with check_expiration=False
    # to get the MRZ data regardless of expiration status
    mrz_data = None
    mrz_extraction_error = None
    try:
        mrz_data = extract_mrz_data(file, check_expiration=False)
        try:
            logger.info("MRZ data extracted: %s", json.dumps(mrz_data, ensure_ascii=False, default=str))
        except Exception:
            logger.debug("Failed to stringify MRZ data for logging.")
    except Exception as e:
        logger.warning(f"MRZ extraction failed: {e}")
        mrz_extraction_error = str(e)
        if not use_ai:
            # If AI is disabled and MRZ failed, re-raise the error
            raise

    if not use_ai:
        if not mrz_data:
            raise Exception("MRZ extraction failed and AI is disabled")
        return mrz_data

    # Step 2: Run AI extraction
    ai_data = None
    ai_error = None
    try:
        ai_result = _extract_with_ai(file)
        if isinstance(ai_result, tuple):
            ai_data, ai_error = ai_result
        else:
            ai_data, ai_error = ai_result, None
    except Exception as e:
        logger.warning(f"AI extraction failed, using MRZ data only: {e}")
        ai_error = str(e)

    if not ai_data:
        if not mrz_data:
            # Both MRZ and AI failed
            raise Exception(f"Failed to extract passport data. MRZ error: {mrz_extraction_error}. AI error: {ai_error}")
        logger.info("No AI data extracted, returning MRZ data only")
        # Add AI error to MRZ data if there was an error
        if ai_error:
            mrz_data["ai_error"] = ai_error
        return mrz_data

    # If MRZ failed but AI succeeded, return AI data mapped to standard keys
    if not mrz_data:
        logger.info("MRZ extraction failed but AI succeeded, returning AI data mapped to standard keys")
        merged_data = _merge_passport_data({}, ai_data, logger)
        merged_data["extraction_method"] = "ai_only"
        merged_data["mrz_error"] = mrz_extraction_error
        return merged_data

    # Step 3: Merge results with comparison logic
    merged_data = _merge_passport_data(mrz_data, ai_data, logger)
    ai_birth_place = None
    if isinstance(ai_data, dict):
        ai_birth_place = ai_data.get("ai_birth_place") or ai_data.get("birth_place")
    if "birth_place" not in merged_data and ai_birth_place not in (None, ""):
        merged_data["birth_place"] = ai_birth_place
    try:
        logger.info("Merged MRZ+AI data: %s", json.dumps(merged_data, ensure_ascii=False, default=str))
    except Exception:
        logger.debug("Failed to stringify merged passport data for logging.")

    return merged_data


def _extract_with_ai(file) -> tuple[Optional[dict], Optional[str]]:
    """
    Extract passport data using AI vision.

    Args:
        file: Uploaded file

    Returns:
        Tuple of (ai_data_dict, error_message):
            - ai_data_dict: dict with AI-extracted passport data or None if extraction fails
            - error_message: error message if extraction failed, None otherwise
    """
    logger = logging.getLogger("passport_ocr")

    try:
        # Import here to avoid circular imports
        from core.services.ai_passport_parser import AIPassportParser

        parser = AIPassportParser()

        # Reset file position if needed
        if hasattr(file, "seek"):
            file.seek(0)

        result = parser.parse_passport_image(file, filename=getattr(file, "name", "passport"))

        if not result.success:
            logger.warning(f"AI passport parsing failed: {result.error_message}")
            return None, result.error_message

        # Convert PassportData to dict
        passport_data = result.passport_data
        ai_dict = {
            "ai_first_name": passport_data.first_name,
            "ai_last_name": passport_data.last_name,
            "ai_full_name": passport_data.full_name,
            "ai_nationality": passport_data.nationality,
            "ai_nationality_code": passport_data.nationality_code,
            "ai_gender": passport_data.gender,
            "ai_date_of_birth": passport_data.date_of_birth,
            "ai_birth_place": passport_data.birth_place,
            "ai_passport_number": passport_data.passport_number,
            "ai_passport_issue_date": passport_data.passport_issue_date,
            "ai_passport_expiration_date": passport_data.passport_expiration_date,
            "ai_issuing_country": passport_data.issuing_country,
            "ai_issuing_country_code": passport_data.issuing_country_code,
            "ai_issuing_authority": passport_data.issuing_authority,
            "ai_height_cm": passport_data.height_cm,
            "ai_eye_color": passport_data.eye_color,
            "ai_address_abroad": passport_data.address_abroad,
            "ai_document_type": passport_data.document_type,
            "ai_confidence_score": passport_data.confidence_score,
        }

        logger.info("AI extraction successful with confidence: %.2f", passport_data.confidence_score or 0.0)
        try:
            logger.info("AI extracted data: %s", json.dumps(ai_dict, ensure_ascii=False, default=str))
        except Exception:
            logger.debug("Failed to stringify AI extracted data for logging.")
        return ai_dict, None

    except Exception as e:
        logger.error(f"Error in AI passport extraction: {e}")
        return None, str(e)


def _merge_passport_data(mrz_data: dict, ai_data: dict, logger: logging.Logger) -> dict:
    """
    Merge MRZ and AI extracted passport data.

    PRIORITY: AI data is preferred over MRZ because AI reads from the visual zone
    which is more accurate than MRZ OCR (which often has errors like Y→7, I→1, O→0).

    Args:
        mrz_data: Data from MRZ extraction
        ai_data: Data from AI extraction
        logger: Logger instance

    Returns:
        dict: Merged passport data with AI data prioritized and mismatch reporting
    """
    merged = {}
    ai_confidence = ai_data.get("ai_confidence_score", 0.0)
    field_mismatches = []  # Track mismatches to report to UI

    def normalize_for_compare(val):
        """Normalize value for comparison (strip, lowercase, handle None)."""
        if val is None:
            return ""
        return str(val).strip().lower()

    def add_field(key, ai_value, mrz_value, prefer_ai=True):
        """Add a field with source tracking and mismatch detection."""
        ai_val = ai_value if ai_value else None
        mrz_val = mrz_value if mrz_value else None

        # Determine which value to use
        if prefer_ai and ai_val:
            merged[key] = ai_val
            merged[f"{key}_source"] = "ai"
        elif mrz_val:
            merged[key] = mrz_val
            merged[f"{key}_source"] = "mrz"
        elif ai_val:
            merged[key] = ai_val
            merged[f"{key}_source"] = "ai"

        # Store both values for reference if they exist
        if ai_val:
            merged[f"ai_{key}"] = ai_val
        if mrz_val:
            merged[f"mrz_{key}"] = mrz_val

        # Check for mismatch
        if ai_val and mrz_val:
            if normalize_for_compare(ai_val) != normalize_for_compare(mrz_val):
                field_mismatches.append(
                    {
                        "field": key,
                        "ai_value": ai_val,
                        "mrz_value": mrz_val,
                        "used": "ai" if (prefer_ai and ai_val) else "mrz",
                    }
                )
                logger.warning(
                    f"Field mismatch for '{key}': AI='{ai_val}' vs MRZ='{mrz_val}' (using {'AI' if prefer_ai else 'MRZ'})"
                )

    # === NAMES (AI preferred) ===
    add_field("names", ai_data.get("ai_first_name"), mrz_data.get("names"), prefer_ai=True)
    add_field("surname", ai_data.get("ai_last_name"), mrz_data.get("surname"), prefer_ai=True)

    # Full name from AI
    if ai_data.get("ai_full_name"):
        merged["full_name"] = ai_data["ai_full_name"]

    # === PASSPORT NUMBER (AI preferred - MRZ often has OCR errors) ===
    add_field("number", ai_data.get("ai_passport_number"), mrz_data.get("number"), prefer_ai=True)

    # === DATES (AI preferred - provides full YYYY-MM-DD) ===
    # Date of birth
    ai_dob = ai_data.get("ai_date_of_birth")
    mrz_dob = mrz_data.get("date_of_birth_yyyy_mm_dd")
    add_field("date_of_birth_yyyy_mm_dd", ai_dob, mrz_dob, prefer_ai=True)

    # Keep raw MRZ date for reference
    if mrz_data.get("date_of_birth"):
        merged["date_of_birth"] = mrz_data["date_of_birth"]
        merged["check_date_of_birth"] = mrz_data.get("check_date_of_birth")

    # Expiration date
    ai_exp = ai_data.get("ai_passport_expiration_date")
    mrz_exp = mrz_data.get("expiration_date_yyyy_mm_dd")
    add_field("expiration_date_yyyy_mm_dd", ai_exp, mrz_exp, prefer_ai=True)

    # Keep raw MRZ expiration for reference
    if mrz_data.get("expiration_date"):
        merged["expiration_date"] = mrz_data["expiration_date"]
        merged["check_expiration_date"] = mrz_data.get("check_expiration_date")

    # Issue date (AI only - not in MRZ)
    if ai_data.get("ai_passport_issue_date"):
        merged["passport_issue_date"] = ai_data["ai_passport_issue_date"]
        # Also store as issue_date_yyyy_mm_dd for frontend compatibility
        merged["issue_date_yyyy_mm_dd"] = ai_data["ai_passport_issue_date"]

    # === GENDER (AI preferred) ===
    add_field("sex", ai_data.get("ai_gender"), mrz_data.get("sex"), prefer_ai=True)

    # === NATIONALITY (prefer MRZ on mismatch) ===
    ai_nationality_name = ai_data.get("ai_nationality")
    ai_nationality_code = ai_data.get("ai_nationality_code") or ai_nationality_name
    mrz_nationality = mrz_data.get("nationality")

    # Normalize to 3-letter code
    if ai_nationality_code and len(str(ai_nationality_code)) == 3 and str(ai_nationality_code).isalpha():
        ai_nationality_code = str(ai_nationality_code).upper()
    else:
        ai_nationality_code = None

    if ai_nationality_code and mrz_nationality:
        if normalize_for_compare(ai_nationality_code) != normalize_for_compare(mrz_nationality):
            merged["nationality"] = mrz_nationality
            merged["nationality_source"] = "mrz"
            merged["ai_nationality_code"] = ai_nationality_code
            if ai_nationality_name:
                merged["ai_nationality_name"] = ai_nationality_name
            field_mismatches.append(
                {
                    "field": "nationality",
                    "ai_value": ai_nationality_code,
                    "mrz_value": mrz_nationality,
                    "used": "mrz",
                }
            )
            logger.warning(
                f"Field mismatch for 'nationality': AI='{ai_nationality_code}' vs MRZ='{mrz_nationality}' (using MRZ)"
            )
        else:
            merged["nationality"] = ai_nationality_code
            merged["nationality_source"] = "ai"
    else:
        add_field("nationality", ai_nationality_code, mrz_nationality, prefer_ai=True)

    # Keep country name
    if mrz_data.get("country_name"):
        merged["country_name"] = mrz_data["country_name"]
    if ai_data.get("ai_issuing_country"):
        merged["country_name"] = ai_data["ai_issuing_country"]

    # === MRZ-SPECIFIC FIELDS (keep from MRZ) ===
    mrz_only_fields = ["mrz_type", "type", "country", "check_number"]
    for field in mrz_only_fields:
        if mrz_data.get(field):
            merged[field] = mrz_data[field]

    # === AI-ONLY FIELDS (not available in MRZ) ===
    ai_only_mappings = [
        ("birth_place", "ai_birth_place"),
        ("issuing_authority", "ai_issuing_authority"),
        ("issuing_country", "ai_issuing_country"),
        ("issuing_country_code", "ai_issuing_country_code"),
        ("height_cm", "ai_height_cm"),
        ("eye_color", "ai_eye_color"),
        ("address_abroad", "ai_address_abroad"),
        ("document_type", "ai_document_type"),
    ]

    for target_key, ai_key in ai_only_mappings:
        if ai_key in ai_data and ai_data[ai_key] not in (None, ""):
            merged[target_key] = ai_data[ai_key]
            logger.debug(f"Added AI-only field {target_key}: {ai_data[ai_key]}")

    # === METADATA ===
    merged["ai_confidence_score"] = ai_confidence
    merged["extraction_method"] = "hybrid_mrz_ai"

    # Add mismatch report for UI
    if field_mismatches:
        merged["field_mismatches"] = field_mismatches
        merged["has_mismatches"] = True
        # Build human-readable mismatch summary
        mismatch_summary = "; ".join(
            [f"{m['field']}: AI='{m['ai_value']}' vs MRZ='{m['mrz_value']}'" for m in field_mismatches]
        )
        merged["mismatch_summary"] = mismatch_summary
        logger.info(f"Field mismatches detected: {mismatch_summary}")
    else:
        merged["has_mismatches"] = False

    return merged
