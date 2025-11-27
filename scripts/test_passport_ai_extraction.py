#!/usr/bin/env python
"""
Integration test script for hybrid passport OCR extraction.
Run this script to test the full pipeline with a real passport image.

Usage:
    python manage.py shell < scripts/test_passport_ai_extraction.py
    OR
    python scripts/test_passport_ai_extraction.py (requires Django setup)
"""

import os
import sys

# Add the project root to the path
project_root = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
sys.path.insert(0, project_root)

# Setup Django
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")

import django

django.setup()

# Now import the modules
from core.utils.passport_ocr import extract_mrz_data, extract_passport_with_ai


def test_mrz_only_extraction():
    """Test MRZ-only extraction."""
    print("=" * 60)
    print("TEST 1: MRZ-Only Extraction (Tesseract + PassportEye)")
    print("=" * 60)

    passport_path = os.path.join(project_root, "tmp", "passport.jpeg")

    if not os.path.exists(passport_path):
        print(f"ERROR: Passport file not found at {passport_path}")
        return None

    try:
        from django.core.files.uploadedfile import SimpleUploadedFile

        with open(passport_path, "rb") as f:
            content = f.read()

        # Create a SimpleUploadedFile that works with the MRZ extractor
        uploaded_file = SimpleUploadedFile(name="passport.jpeg", content=content, content_type="image/jpeg")

        mrz_data = extract_mrz_data(uploaded_file, check_expiration=False)

        print("\nMRZ Data Extracted:")
        print("-" * 40)
        for key, value in sorted(mrz_data.items()):
            print(f"  {key}: {value}")

        return mrz_data

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_hybrid_extraction():
    """Test hybrid MRZ + AI extraction."""
    print("\n" + "=" * 60)
    print("TEST 2: Hybrid Extraction (MRZ + AI Vision)")
    print("=" * 60)

    passport_path = os.path.join(project_root, "tmp", "passport.jpeg")

    if not os.path.exists(passport_path):
        print(f"ERROR: Passport file not found at {passport_path}")
        return None

    try:
        from django.core.files.uploadedfile import SimpleUploadedFile

        with open(passport_path, "rb") as f:
            content = f.read()

        # Create a SimpleUploadedFile that works with the MRZ extractor
        uploaded_file = SimpleUploadedFile(name="passport.jpeg", content=content, content_type="image/jpeg")

        hybrid_data = extract_passport_with_ai(uploaded_file, use_ai=True)

        print("\nHybrid Data Extracted:")
        print("-" * 40)

        # Separate MRZ fields from AI fields
        mrz_fields = []
        ai_fields = []

        for key, value in sorted(hybrid_data.items()):
            if key.startswith("ai_") or key in [
                "birth_place",
                "passport_issue_date",
                "issuing_authority",
                "height_cm",
                "eye_color",
                "address_abroad",
                "issuing_country",
                "extraction_method",
            ]:
                ai_fields.append((key, value))
            else:
                mrz_fields.append((key, value))

        print("\nMRZ Fields:")
        for key, value in mrz_fields:
            print(f"  {key}: {value}")

        print("\nAI-Enhanced Fields:")
        for key, value in ai_fields:
            print(f"  {key}: {value}")

        return hybrid_data

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return None


def test_ai_parser_directly():
    """Test AI parser directly."""
    print("\n" + "=" * 60)
    print("TEST 3: Direct AI Parser Test")
    print("=" * 60)

    from core.services.ai_passport_parser import AIPassportParser

    passport_path = os.path.join(project_root, "tmp", "passport.jpeg")

    if not os.path.exists(passport_path):
        print(f"ERROR: Passport file not found at {passport_path}")
        return None

    try:
        parser = AIPassportParser()
        print(f"Parser initialized with model: {parser.model}")

        with open(passport_path, "rb") as f:
            image_bytes = f.read()

        result = parser.parse_passport_image(image_bytes, filename="passport.jpeg")

        if result.success:
            print("\nAI Parsing Successful!")
            print(f"Confidence Score: {result.passport_data.confidence_score:.2%}")
            print("-" * 40)

            data = result.passport_data
            fields = [
                ("First Name", data.first_name),
                ("Last Name", data.last_name),
                ("Full Name", data.full_name),
                ("Gender", data.gender),
                ("Nationality", f"{data.nationality} ({data.nationality_code})"),
                ("Date of Birth", data.date_of_birth),
                ("Birth Place", data.birth_place),
                ("Passport Number", data.passport_number),
                ("Issue Date", data.passport_issue_date),
                ("Expiration Date", data.passport_expiration_date),
                ("Issuing Country", f"{data.issuing_country} ({data.issuing_country_code})"),
                ("Issuing Authority", data.issuing_authority),
                ("Height (cm)", data.height_cm),
                ("Eye Color", data.eye_color),
                ("Address Abroad", data.address_abroad),
                ("Document Type", data.document_type),
            ]

            for label, value in fields:
                print(f"  {label}: {value}")

            return result
        else:
            print(f"\nAI Parsing Failed: {result.error_message}")
            return None

    except Exception as e:
        print(f"ERROR: {e}")
        import traceback

        traceback.print_exc()
        return None


if __name__ == "__main__":
    print("\n" + "#" * 60)
    print("# PASSPORT HYBRID OCR EXTRACTION - INTEGRATION TEST")
    print("#" * 60)

    # Run tests
    mrz_result = test_mrz_only_extraction()
    hybrid_result = test_hybrid_extraction()
    ai_result = test_ai_parser_directly()

    # Summary
    print("\n" + "=" * 60)
    print("SUMMARY")
    print("=" * 60)
    print(f"MRZ-Only Extraction: {'SUCCESS' if mrz_result else 'FAILED'}")
    print(f"Hybrid Extraction:   {'SUCCESS' if hybrid_result else 'FAILED'}")
    print(f"Direct AI Parser:    {'SUCCESS' if ai_result else 'FAILED'}")

    if hybrid_result:
        if hybrid_result.get("extraction_method") == "hybrid_mrz_ai":
            print("\n✓ Hybrid extraction worked correctly!")
            print(f"  AI Confidence: {hybrid_result.get('ai_confidence_score', 0):.2%}")

            # Check for AI-only fields
            ai_fields_present = []
            if hybrid_result.get("birth_place"):
                ai_fields_present.append("birth_place")
            if hybrid_result.get("passport_issue_date"):
                ai_fields_present.append("passport_issue_date")
            if hybrid_result.get("issuing_authority"):
                ai_fields_present.append("issuing_authority")
            if hybrid_result.get("height_cm"):
                ai_fields_present.append("height_cm")
            if hybrid_result.get("eye_color"):
                ai_fields_present.append("eye_color")

            if ai_fields_present:
                print(f"  AI-enhanced fields extracted: {', '.join(ai_fields_present)}")
        else:
            print("\n⚠ Hybrid extraction fell back to MRZ-only")
