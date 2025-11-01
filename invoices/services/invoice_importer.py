"""
Invoice Importer Service
Orchestrates the import process: parsing, matching, and creating invoices.
"""

import logging
from dataclasses import dataclass
from datetime import datetime
from decimal import Decimal
from typing import Optional, Tuple

from django.db import transaction
from django.db.models import Q

from customers.models import Customer
from invoices.models import Invoice, InvoiceLineItem
from invoices.services.llm_invoice_parser import LLMInvoiceParser, ParsedInvoiceResult
from products.models import Product

logger = logging.getLogger(__name__)


@dataclass
class ImportResult:
    """Result of an invoice import attempt."""

    success: bool
    status: str  # 'imported', 'duplicate', 'error'
    message: str
    invoice: Optional[Invoice] = None
    customer: Optional[Customer] = None
    errors: list = None

    def __post_init__(self):
        if self.errors is None:
            self.errors = []


class InvoiceImporter:
    """
    Service to import invoices from uploaded files using multimodal AI.
    """

    def __init__(self, user=None):
        """
        Initialize importer.

        Args:
            user: Django user performing the import (for audit trail)
        """
        self.user = user
        self.llm_parser = LLMInvoiceParser()

    def import_from_file(self, uploaded_file, filename: str = None) -> ImportResult:
        """
        Import an invoice from an uploaded file.

        Args:
            uploaded_file: Django UploadedFile object
            filename: Optional filename override

        Returns:
            ImportResult with status and details
        """
        filename = filename or uploaded_file.name
        logger.info(f"Starting import for file: {filename}")

        try:
            # Step 1: Parse invoice directly with multimodal vision
            parsed_result = self.llm_parser.parse_invoice_file(uploaded_file, filename)
            if not parsed_result:
                return ImportResult(
                    success=False,
                    status="error",
                    message=f"Failed to parse invoice from {filename}",
                    errors=["Multimodal parsing failed"],
                )

            # Step 2: Validate parsed data
            is_valid, validation_errors = self.llm_parser.validate_parsed_data(parsed_result)
            if not is_valid:
                return ImportResult(
                    success=False,
                    status="error",
                    message=f"Invalid invoice data in {filename}",
                    errors=validation_errors,
                )

            logger.info(
                f"Successfully parsed invoice {parsed_result.invoice.invoice_no} with confidence {parsed_result.confidence_score:.2f}"
            )

            # Step 3: Check for duplicate invoice
            duplicate_invoice = self._check_duplicate_invoice(parsed_result)
            if duplicate_invoice:
                return ImportResult(
                    success=False,
                    status="duplicate",
                    message=f"Invoice {parsed_result.invoice.invoice_no} already exists",
                    invoice=duplicate_invoice,
                )

            # Step 4: Find or create customer
            customer, created = self._find_or_create_customer(parsed_result)
            if not customer:
                return ImportResult(
                    success=False,
                    status="error",
                    message=f"Failed to create/find customer for {filename}",
                    errors=["Customer creation failed"],
                )

            customer_status = "created" if created else "matched"
            logger.info(f"Customer {customer_status}: {customer.full_name}")

            # Step 5: Create invoice with line items
            invoice = self._create_invoice(parsed_result, customer, filename)
            if not invoice:
                return ImportResult(
                    success=False,
                    status="error",
                    message=f"Failed to create invoice from {filename}",
                    errors=["Invoice creation failed"],
                )

            logger.info(f"Successfully imported invoice {invoice.invoice_no_display}")

            return ImportResult(
                success=True,
                status="imported",
                message=f"Successfully imported invoice {invoice.invoice_no_display} for {customer.full_name}",
                invoice=invoice,
                customer=customer,
            )

        except Exception as e:
            logger.error(f"Error importing {filename}: {str(e)}", exc_info=True)
            return ImportResult(
                success=False,
                status="error",
                message=f"Unexpected error importing {filename}: {str(e)}",
                errors=[str(e)],
            )

    def _check_duplicate_invoice(self, parsed_result: ParsedInvoiceResult) -> Optional[Invoice]:
        """
        Check if invoice already exists in database.
        Match by invoice_no and customer name/phone.
        """
        invoice_no = parsed_result.invoice.invoice_no
        customer_name = parsed_result.customer.full_name
        customer_phone = parsed_result.customer.phone or parsed_result.customer.mobile_phone

        # Try to find existing invoice
        query = Q(invoice_no=invoice_no)

        # Add customer matching
        if customer_phone:
            query &= Q(customer__telephone=customer_phone) | Q(customer__whatsapp=customer_phone)
        else:
            # Match by name if no phone
            first_name = parsed_result.customer.first_name or customer_name.split()[0]
            last_name = parsed_result.customer.last_name or (
                customer_name.split()[-1] if len(customer_name.split()) > 1 else ""
            )
            query &= Q(customer__first_name__iexact=first_name, customer__last_name__iexact=last_name)

        existing_invoice = Invoice.objects.filter(query).first()
        return existing_invoice

    def _find_or_create_customer(self, parsed_result: ParsedInvoiceResult) -> Tuple[Optional[Customer], bool]:
        """
        Find existing customer or create new one.
        Matching priority: phone > email > name (exact)

        Returns:
            (Customer instance, created_flag)
        """
        customer_data = parsed_result.customer

        # Try to find by phone (highest priority)
        phone = customer_data.phone or customer_data.mobile_phone
        if phone:
            customer = Customer.objects.filter(Q(telephone=phone) | Q(whatsapp=phone) | Q(telegram=phone)).first()
            if customer:
                logger.info(f"Matched customer by phone: {customer.full_name}")
                return customer, False

        # Try to find by email
        if customer_data.email:
            customer = Customer.objects.filter(email__iexact=customer_data.email).first()
            if customer:
                logger.info(f"Matched customer by email: {customer.full_name}")
                return customer, False

        # Try to find by name (exact match)
        first_name = customer_data.first_name or customer_data.full_name.split()[0]
        last_name = customer_data.last_name or (
            customer_data.full_name.split()[-1] if len(customer_data.full_name.split()) > 1 else ""
        )

        if first_name and last_name:
            customer = Customer.objects.filter(first_name__iexact=first_name, last_name__iexact=last_name).first()
            if customer:
                logger.info(f"Matched customer by name: {customer.full_name}")
                return customer, False

        # No match found, create new customer
        logger.info(f"Creating new customer: {customer_data.full_name}")
        return self._create_customer(customer_data), True

    def _create_customer(self, customer_data) -> Optional[Customer]:
        """
        Create a new customer from parsed data.
        """
        try:
            # Parse name
            full_name = customer_data.full_name
            name_parts = full_name.split()

            first_name = customer_data.first_name or name_parts[0]
            last_name = customer_data.last_name or (name_parts[-1] if len(name_parts) > 1 else name_parts[0])

            # Use phone or mobile_phone
            phone = customer_data.phone or customer_data.mobile_phone

            # Create customer with minimal required fields
            customer = Customer.objects.create(
                first_name=first_name,
                last_name=last_name,
                email=customer_data.email or None,
                telephone=phone,
                whatsapp=phone,  # Assume same as phone
                title="",  # Empty string (required choice field)
                birthdate="2000-01-01",  # Default birthdate (required field)
                notify_documents_expiration=False,
                active=True,
            )

            logger.info(f"Created customer: {customer.full_name} (ID: {customer.pk})")
            return customer

        except Exception as e:
            logger.error(f"Error creating customer: {str(e)}", exc_info=True)
            return None

    @transaction.atomic
    def _create_invoice(
        self, parsed_result: ParsedInvoiceResult, customer: Customer, filename: str
    ) -> Optional[Invoice]:
        """
        Create invoice with line items from parsed data.
        """
        try:
            invoice_data = parsed_result.invoice

            # Parse dates
            invoice_date = datetime.strptime(invoice_data.invoice_date, "%Y-%m-%d").date()
            due_date = datetime.strptime(invoice_data.due_date, "%Y-%m-%d").date()

            # Determine status based on payment_status
            status = Invoice.CREATED
            if invoice_data.payment_status:
                payment_status_lower = invoice_data.payment_status.lower()
                if "paid" in payment_status_lower or "full payment" in payment_status_lower:
                    status = Invoice.PAID
                elif "pending" in payment_status_lower:
                    status = Invoice.PENDING_PAYMENT

            # Create invoice
            invoice = Invoice(
                customer=customer,
                invoice_no=int(invoice_data.invoice_no),
                invoice_date=invoice_date,
                due_date=due_date,
                status=status,
                notes=invoice_data.notes or "",
                imported=True,
                imported_from_file=filename,
                raw_extracted_data=parsed_result.raw_response,
                mobile_phone=parsed_result.customer.mobile_phone,
                bank_details=invoice_data.bank_details,
                created_by=self.user,
                updated_by=self.user,
            )

            # Don't call save() yet, let the model's save() calculate total_amount
            # But we need to save first to get an ID for line items
            invoice.save()

            # Create line items
            for item_data in parsed_result.line_items:
                # Try to match product by code
                product = None
                if item_data.code:
                    product = Product.objects.filter(code__iexact=item_data.code).first()

                InvoiceLineItem.objects.create(
                    invoice=invoice,
                    code=item_data.code,
                    description=item_data.description,
                    quantity=Decimal(str(item_data.quantity)),
                    unit_price=Decimal(str(item_data.unit_price)),
                    amount=Decimal(str(item_data.amount)),
                    product=product,
                )

            # Recalculate and save total (this will trigger save() again)
            invoice.save()

            logger.info(
                f"Created invoice {invoice.invoice_no_display} with "
                f"{len(parsed_result.line_items)} line items, total: {invoice.total_amount}"
            )

            return invoice

        except Exception as e:
            logger.error(f"Error creating invoice: {str(e)}", exc_info=True)
            return None
