#!/usr/bin/env python
"""
Test script for parallel invoice import with race condition testing.
Tests database locking and concurrent customer/invoice creation.
"""

import os
import sys
from pathlib import Path

import pytest

# Use pytest-django database fixture for these concurrency tests
pytestmark = pytest.mark.django_db(transaction=True)

import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from io import BytesIO

from django.contrib.auth import get_user_model
from django.db import connection
from django.test.utils import CaptureQueriesContext

from customers.models import Customer
from invoices.models import Invoice
from invoices.services.invoice_importer import InvoiceImporter

User = get_user_model()


def create_test_invoice_data(invoice_no, customer_name="John Doe", customer_phone="+1234567890"):
    """Create mock parsed invoice data for testing."""
    from invoices.services.llm_invoice_parser import CustomerData, InvoiceData, InvoiceLineItemData, ParsedInvoiceResult

    customer = CustomerData(
        full_name=customer_name,
        first_name=customer_name.split()[0],
        last_name=customer_name.split()[-1] if len(customer_name.split()) > 1 else customer_name,
        email=f"{customer_name.lower().replace(' ', '.')}@test.com",
        phone=customer_phone,
        mobile_phone=customer_phone,
    )

    invoice = InvoiceData(
        invoice_no=str(invoice_no),
        invoice_date="2025-11-01",
        due_date="2025-11-30",
        total_amount=1000.00,
        notes="Test invoice for parallel import",
    )

    line_items = [
        InvoiceLineItemData(
            code=f"VISA-{invoice_no}",
            description="Test Visa Service",
            quantity=1,
            unit_price=1000.00,
            amount=1000.00,
        )
    ]

    return ParsedInvoiceResult(
        customer=customer,
        invoice=invoice,
        line_items=line_items,
        confidence_score=0.95,
        raw_response={"test": "data"},
    )


def test_concurrent_customer_creation():
    """Test that concurrent imports with same customer don't create duplicates."""
    print("\n" + "=" * 80)
    print("TEST 1: Concurrent Customer Creation (Race Condition Prevention)")
    print("=" * 80)

    # Clean up existing test data
    Customer.objects.filter(email__contains="john.doe@test.com").delete()
    Invoice.objects.filter(invoice_no__in=[1001, 1002, 1003]).delete()

    user = User.objects.first()

    def import_with_same_customer(invoice_no):
        """Import invoice with the same customer details."""
        print(f"  Thread {invoice_no}: Starting import...")
        importer = InvoiceImporter(user=user)

        # Create mock parsed data with SAME customer but different invoice
        parsed_data = create_test_invoice_data(
            invoice_no=invoice_no, customer_name="John Doe", customer_phone="+1234567890"
        )

        # Simulate the import process (without actual file)
        customer, created = importer._find_or_create_customer(parsed_data)
        print(f"  Thread {invoice_no}: Customer {'CREATED' if created else 'MATCHED'} - ID: {customer.pk}")
        return customer

    # Run 3 concurrent imports with same customer
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(import_with_same_customer, i) for i in [1001, 1002, 1003]]
        customers = [f.result() for f in as_completed(futures)]

    elapsed = time.time() - start_time

    # Check results
    customer_ids = [c.pk for c in customers]
    unique_customers = len(set(customer_ids))

    print(f"\n  Results:")
    print(f"  - Execution time: {elapsed:.2f}s")
    print(f"  - Customer IDs: {customer_ids}")
    print(f"  - Unique customers: {unique_customers}")
    print(f"  - Database customers count: {Customer.objects.filter(email__contains='john.doe@test.com').count()}")

    if unique_customers == 1:
        print("  ✅ PASS: No duplicate customers created!")
    else:
        print(f"  ❌ FAIL: Created {unique_customers} customers instead of 1!")

    return unique_customers == 1


def test_concurrent_invoice_creation():
    """Test that duplicate invoice detection works in parallel."""
    print("\n" + "=" * 80)
    print("TEST 2: Concurrent Invoice Duplicate Detection")
    print("=" * 80)

    # Clean up
    Invoice.objects.filter(invoice_no=2001).delete()
    Customer.objects.filter(email__contains="jane.smith@test.com").delete()

    user = User.objects.first()

    def try_import_duplicate(attempt_no):
        """Try to import the same invoice multiple times."""
        print(f"  Thread {attempt_no}: Attempting import...")
        importer = InvoiceImporter(user=user)

        # Same invoice number for all attempts
        parsed_data = create_test_invoice_data(
            invoice_no=2001, customer_name="Jane Smith", customer_phone="+9876543210"
        )

        # Check for duplicate
        duplicate = importer._check_duplicate_invoice(parsed_data)

        if duplicate:
            print(f"  Thread {attempt_no}: Duplicate detected - Invoice ID: {duplicate.pk}")
            return "duplicate", duplicate.pk
        else:
            # Try to create (first one should succeed)
            customer, _ = importer._find_or_create_customer(parsed_data)
            invoice = importer._create_invoice(parsed_data, customer, f"test_{attempt_no}.pdf")
            if invoice:
                print(f"  Thread {attempt_no}: Invoice CREATED - ID: {invoice.pk}")
                return "created", invoice.pk
            else:
                print(f"  Thread {attempt_no}: Failed to create")
                return "error", None

    # Run 5 concurrent attempts to create same invoice
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=5) as executor:
        futures = [executor.submit(try_import_duplicate, i) for i in range(1, 6)]
        results = [f.result() for f in as_completed(futures)]

    elapsed = time.time() - start_time

    # Check results
    created_count = sum(1 for status, _ in results if status == "created")
    duplicate_count = sum(1 for status, _ in results if status == "duplicate")

    print(f"\n  Results:")
    print(f"  - Execution time: {elapsed:.2f}s")
    print(f"  - Created: {created_count}")
    print(f"  - Duplicates detected: {duplicate_count}")
    print(f"  - Database invoices with #2001: {Invoice.objects.filter(invoice_no=2001).count()}")

    if created_count == 1 and Invoice.objects.filter(invoice_no=2001).count() == 1:
        print("  ✅ PASS: Only one invoice created, duplicates properly detected!")
    else:
        print(f"  ❌ FAIL: Created {created_count} invoices instead of 1!")

    return created_count == 1


def test_parallel_performance():
    """Test performance improvement with parallel processing."""
    print("\n" + "=" * 80)
    print("TEST 3: Parallel vs Sequential Performance")
    print("=" * 80)

    # Clean up
    Invoice.objects.filter(invoice_no__in=range(3001, 3011)).delete()
    Customer.objects.filter(email__contains="@parallel-test.com").delete()

    user = User.objects.first()

    def import_single(invoice_no):
        """Import a single invoice."""
        importer = InvoiceImporter(user=user)
        parsed_data = create_test_invoice_data(
            invoice_no=invoice_no, customer_name=f"Customer {invoice_no}", customer_phone=f"+100000{invoice_no}"
        )

        customer, _ = importer._find_or_create_customer(parsed_data)
        invoice = importer._create_invoice(parsed_data, customer, f"test_{invoice_no}.pdf")
        return invoice is not None

    # Sequential processing
    print("\n  Sequential processing (10 invoices)...")
    start_time = time.time()
    for i in range(3001, 3011):
        import_single(i)
    sequential_time = time.time() - start_time
    print(f"  - Time: {sequential_time:.2f}s")

    # Clean up for parallel test
    Invoice.objects.filter(invoice_no__in=range(3001, 3011)).delete()
    Customer.objects.filter(email__contains="@parallel-test.com").delete()

    # Parallel processing (max 3 workers as configured)
    print("\n  Parallel processing (10 invoices, 3 workers)...")
    start_time = time.time()
    with ThreadPoolExecutor(max_workers=3) as executor:
        futures = [executor.submit(import_single, i) for i in range(3001, 3011)]
        results = [f.result() for f in as_completed(futures)]
    parallel_time = time.time() - start_time
    print(f"  - Time: {parallel_time:.2f}s")

    speedup = sequential_time / parallel_time if parallel_time > 0 else 0

    print(f"\n  Results:")
    print(f"  - Sequential: {sequential_time:.2f}s")
    print(f"  - Parallel: {parallel_time:.2f}s")
    print(f"  - Speedup: {speedup:.2f}x")
    print(f"  - Successfully imported: {sum(results)}/10")

    if speedup > 1.5:
        print(f"  ✅ PASS: Good speedup with parallel processing!")
    elif speedup > 1.0:
        print(f"  ⚠️  PARTIAL: Some speedup, but could be better")
    else:
        print(f"  ❌ FAIL: No speedup achieved")

    return speedup > 1.0


def test_database_locking():
    """Test that database locking is actually being used."""
    print("\n" + "=" * 80)
    print("TEST 4: Database Locking Verification")
    print("=" * 80)

    user = User.objects.first()
    importer = InvoiceImporter(user=user)

    # Create a test customer
    test_customer = Customer.objects.create(
        first_name="Lock",
        last_name="Test",
        email="lock.test@example.com",
        telephone="+1111111111",
        whatsapp="+1111111111",
        title="",
        birthdate="2000-01-01",
        active=True,
    )

    print(f"\n  Created test customer ID: {test_customer.pk}")

    # Test that select_for_update is called
    with CaptureQueriesContext(connection) as queries:
        parsed_data = create_test_invoice_data(invoice_no=4001, customer_name="Lock Test", customer_phone="+1111111111")
        customer, created = importer._find_or_create_customer(parsed_data)

    # Check if SELECT FOR UPDATE was used
    select_for_update_used = any("FOR UPDATE" in query["sql"] for query in queries.captured_queries)

    print(f"\n  Results:")
    print(f"  - Queries executed: {len(queries.captured_queries)}")
    print(f"  - SELECT FOR UPDATE used: {select_for_update_used}")

    if select_for_update_used:
        print("  ✅ PASS: Database row locking is active!")

        # Show the actual query
        for query in queries.captured_queries:
            if "FOR UPDATE" in query["sql"]:
                print(f"\n  Lock query: {query['sql'][:200]}...")
    else:
        print("  ❌ FAIL: No row locking detected!")

    # Cleanup
    test_customer.delete()

    return select_for_update_used


def main():
    """Run all tests."""
    print("\n" + "=" * 80)
    print("PARALLEL INVOICE IMPORT TESTS")
    print("=" * 80)
    print("\nTesting parallel processing with race condition prevention...")

    results = {
        "Customer Race Condition": test_concurrent_customer_creation(),
        "Invoice Duplicate Detection": test_concurrent_invoice_creation(),
        "Parallel Performance": test_parallel_performance(),
        "Database Locking": test_database_locking(),
    }

    print("\n" + "=" * 80)
    print("FINAL RESULTS")
    print("=" * 80)

    passed = sum(results.values())
    total = len(results)

    for test_name, passed in results.items():
        status = "✅ PASS" if passed else "❌ FAIL"
        print(f"  {status}: {test_name}")

    print(f"\n  Total: {passed}/{total} tests passed")

    if passed == total:
        print("\n  🎉 All tests passed! Parallel import is working correctly.")
    else:
        print(f"\n  ⚠️  {total - passed} test(s) failed. Review the output above.")

    return passed == total


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n❌ Error running tests: {str(e)}")
        import traceback

        traceback.print_exc()
        sys.exit(1)
