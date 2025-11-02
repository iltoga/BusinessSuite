#!/usr/bin/env python
"""
Test invoice extraction from both Excel and PDF files using configured LLM provider.
"""

import os
import sys
from pathlib import Path

import django

# Setup Django environment
sys.path.insert(0, str(Path(__file__).parent.parent.parent))
os.environ.setdefault("DJANGO_SETTINGS_MODULE", "business_suite.settings.dev")
django.setup()

from django.conf import settings

from invoices.services.llm_invoice_parser import LLMInvoiceParser

# ============================================================================
# TEST CONFIGURATION - Override these to test different models/providers
# ============================================================================
# TEST_MODEL = "openai/gpt-5-nano" # good
# TEST_MODEL = "google/gemini-2.0-flash-lite-001" # good
# TEST_MODEL = "mistralai/mistral-small-3.2-24b-instruct" # good
TEST_MODEL = "google/gemini-2.5-flash-lite"
TEST_PROVIDER = None  # Set to "openrouter" or "openai" to override


def test_invoice_extraction():
    """Test invoice extraction using configured LLM provider and model."""

    print("=" * 80)
    print("INVOICE EXTRACTION TEST")
    print("=" * 80)

    # Initialize parser - use test overrides if provided, otherwise use settings
    if TEST_PROVIDER is not None:
        use_openrouter = TEST_PROVIDER == "openrouter"
        print(f"\n⚙️  Using TEST_PROVIDER override: {TEST_PROVIDER}")
    else:
        use_openrouter = getattr(settings, "LLM_PROVIDER", "openrouter") == "openrouter"

    if TEST_MODEL is not None:
        parser = LLMInvoiceParser(use_openrouter=use_openrouter, model=TEST_MODEL)
        print(f"⚙️  Using TEST_MODEL override: {TEST_MODEL}")
    else:
        parser = LLMInvoiceParser(use_openrouter=use_openrouter)

    provider_name = "OpenRouter" if use_openrouter else "OpenAI Direct"
    print(f"\nProvider: {provider_name}")
    print(f"Model: {parser.model}")

    # Test files
    test_files = [
        ("tmp/202634Inv_Daniel Cain Frankel_CFK-12.xlsx", "xlsx"),
        ("tmp/202634Inv_Daniel Cain Frankel_CFK-12.pdf", "pdf"),
    ]

    results = {}

    for file_path, file_type in test_files:
        print("\n" + "=" * 80)
        print(f"Testing: {file_path}")
        print("=" * 80)

        full_path = Path(file_path)
        if not full_path.exists():
            print(f"❌ File not found: {file_path}")
            continue

        # Read file
        with open(full_path, "rb") as f:
            file_content = f.read()

        print(f"\nFile size: {len(file_content):,} bytes")
        print(f"File type: {file_type}")
        print(f"\nParsing with {parser.model}...")

        # Parse invoice
        try:
            result = parser.parse_invoice_file(file_content=file_content, filename=full_path.name, file_type=file_type)

            if result:
                print("\n✅ SUCCESS: Invoice parsed successfully!")

                # Validate
                is_valid, errors = parser.validate_parsed_data(result)

                print(f"\n📊 EXTRACTED DATA:")
                print(f"\n  Customer:")
                print(f"    - Full Name: {result.customer.full_name}")
                print(f"    - First Name: {result.customer.first_name}")
                print(f"    - Last Name: {result.customer.last_name}")
                print(f"    - Email: {result.customer.email}")
                print(f"    - Phone: {result.customer.phone}")

                print(f"\n  Invoice:")
                print(f"    - Invoice No: {result.invoice.invoice_no}")
                print(f"    - Invoice Date: {result.invoice.invoice_date}")
                print(f"    - Due Date: {result.invoice.due_date}")
                print(f"    - Total Amount: {result.invoice.total_amount:,.2f}")
                print(f"    - Payment Status: {result.invoice.payment_status}")

                print(f"\n  Line Items ({len(result.line_items)} items):")
                for i, item in enumerate(result.line_items, 1):
                    print(f"    {i}. {item.code} - {item.description}")
                    print(f"       Qty: {item.quantity}, Price: {item.unit_price:,.2f}, Amount: {item.amount:,.2f}")

                if result.invoice.bank_details:
                    print(f"\n  Bank Details:")
                    bank = result.invoice.bank_details
                    print(f"    - Bank: {bank.get('bank_name')}")
                    print(f"    - Beneficiary: {bank.get('beneficiary_name')}")
                    print(f"    - Account: {bank.get('account_number')}")

                print(f"\n  Confidence Score: {result.confidence_score:.2%}")

                print(f"\n✓ VALIDATION:")
                if is_valid:
                    print("  ✅ All validations passed!")
                else:
                    print(f"  ⚠️  Validation issues found:")
                    for error in errors:
                        print(f"    - {error}")

                # Store result for comparison
                results[file_type] = {
                    "success": True,
                    "customer_name": result.customer.full_name,
                    "invoice_no": result.invoice.invoice_no,
                    "total_amount": result.invoice.total_amount,
                    "line_items_count": len(result.line_items),
                    "confidence": result.confidence_score,
                    "valid": is_valid,
                }

            else:
                print("\n❌ FAILED: Could not parse invoice")
                results[file_type] = {"success": False}

        except Exception as e:
            print(f"\n❌ ERROR: {str(e)}")
            import traceback

            traceback.print_exc()
            results[file_type] = {"success": False, "error": str(e)}

    # Compare results
    print("\n" + "=" * 80)
    print("COMPARISON: Excel vs PDF Extraction")
    print("=" * 80)

    if "xlsx" in results and "pdf" in results:
        xlsx_result = results["xlsx"]
        pdf_result = results["pdf"]

        if xlsx_result.get("success") and pdf_result.get("success"):
            print(f"\n✅ Both files parsed successfully!")

            # Compare key fields
            comparisons = [
                ("Customer Name", xlsx_result.get("customer_name"), pdf_result.get("customer_name")),
                ("Invoice Number", xlsx_result.get("invoice_no"), pdf_result.get("invoice_no")),
                ("Total Amount", xlsx_result.get("total_amount"), pdf_result.get("total_amount")),
                ("Line Items Count", xlsx_result.get("line_items_count"), pdf_result.get("line_items_count")),
                ("Confidence Score", f"{xlsx_result.get('confidence'):.2%}", f"{pdf_result.get('confidence'):.2%}"),
            ]

            print("\n  Field Comparison:")
            all_match = True
            for field, xlsx_val, pdf_val in comparisons:
                match = "✓" if xlsx_val == pdf_val else "✗"
                print(f"    {match} {field}:")
                print(f"      Excel: {xlsx_val}")
                print(f"      PDF:   {pdf_val}")
                if xlsx_val != pdf_val:
                    all_match = False

            if all_match:
                print("\n  🎉 Perfect match! Both extractions identical.")
            else:
                print("\n  ⚠️  Some differences found between Excel and PDF extractions.")
        else:
            print(f"\n  Excel: {'✅' if xlsx_result.get('success') else '❌'}")
            print(f"  PDF:   {'✅' if pdf_result.get('success') else '❌'}")

    # Summary
    print("\n" + "=" * 80)
    print("SUMMARY")
    print("=" * 80)

    total_tests = len(results)
    successful = sum(1 for r in results.values() if r.get("success"))

    print(f"\n  Total tests: {total_tests}")
    print(f"  Successful: {successful}")
    print(f"  Failed: {total_tests - successful}")
    print(f"\n  Provider: {provider_name}")
    print(f"  Model: {parser.model}")

    if successful == total_tests:
        print("\n  🎉 All tests passed! Invoice extraction is working correctly.")
        return True
    else:
        print("\n  ⚠️  Some tests failed. Check the output above.")
        return False


if __name__ == "__main__":
    try:
        success = test_invoice_extraction()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Fatal error: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
