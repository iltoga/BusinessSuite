from django.core.management.base import BaseCommand

from products.models import DocumentType


class Command(BaseCommand):
    help = "Populate the DocumentType model"

    def handle(self, *args, **kwargs):
        document_types = [
            {
                "name": "Address",
                "description": "Indonesian address details",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": False,
                "has_details": True,
                "is_in_required_documents": True,
            },
            {
                "name": "Bank Statement",
                "description": "Screenshot or PDF of a recent bank statement displaying bank name, account owner, account number, and balance",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": False,
                "is_in_required_documents": True,
            },
            {
                "name": "Flight Ticket",
                "description": "Copy of the flight ticket out of Indonesia displaying date, flight number, and booking code",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": True,
                "is_in_required_documents": True,
            },
            {
                "name": "Passport",
                "description": "Passport with a validity of at least six months",
                "has_ocr_check": True,
                "has_expiration_date": True,
                "has_doc_number": True,
                "has_file": True,
                "has_details": True,
                "is_in_required_documents": True,
            },
            {
                "name": "Selfie Photo",
                "description": "Selfie photo taken with a cell phone camera",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": False,
                "is_in_required_documents": True,
            },
            {
                "name": "Covid-19 Certificate",
                "description": "Covid-19 vaccination certificate - minimal 2 doses",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": True,
                "is_in_required_documents": True,
            },
            {
                "name": "Arrival Stamp",
                "description": "Stamp from Airport",
                "has_ocr_check": False,
                "has_expiration_date": True,
                "has_doc_number": False,
                "has_file": True,
                "has_details": False,
                "is_in_required_documents": True,
            },
            {
                "name": "Processed Visa Stamp",
                "description": "Stamp of the visa on the passport processed by immigration",
                "has_ocr_check": False,
                "has_expiration_date": True,
                "has_doc_number": False,
                "has_file": True,
                "has_details": True,
                "is_in_required_documents": False,
            },
        ]

        for doc_type in document_types:
            if not DocumentType.objects.filter(name=doc_type["name"]).exists():
                DocumentType.objects.create(**doc_type)
                self.stdout.write(self.style.SUCCESS(f"Created document type: {doc_type['name']}"))
            else:
                self.stdout.write(self.style.WARNING(f"Document type '{doc_type['name']}' already exists. Skipping."))

        self.stdout.write(self.style.SUCCESS("Finished populating DocumentType table"))
