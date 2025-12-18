from django.core.management.base import BaseCommand

from products.models import DocumentType


class Command(BaseCommand):
    help = "Populate the DocumentType model"

    def handle(self, *args, **kwargs):
        document_types = [
            # Required documents
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
                "name": "Arrival Stamp",
                "description": "Immigration arrival stamp on the passport showing entry date into Indonesia",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": False,
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
                "name": "ITK",
                "description": "Izin Tinggal Kunjungan, is a short-term visit stay permit for foreigners in Indonesia, issued upon arrival in the country",
                "has_ocr_check": False,
                "has_expiration_date": True,
                "has_doc_number": True,
                "has_file": True,
                "has_details": True,
                "is_in_required_documents": True,
            },
            {
                "name": "Passport",
                "description": "Passport biodata page with a validity of at least six months (twelve months for 180-day visas)",
                "has_ocr_check": True,
                "has_expiration_date": True,
                "has_doc_number": True,
                "has_file": True,
                "has_details": True,
                "is_in_required_documents": True,
            },
            {
                "name": "Passport Sponsor",
                "description": "Passport of the Indonesian sponsor",
                "has_ocr_check": True,
                "has_expiration_date": True,
                "has_doc_number": True,
                "has_file": True,
                "has_details": False,
                "is_in_required_documents": True,
            },
            {
                "name": "Proof of Payment",
                "description": "Proof of payment for the visa application fee",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": False,
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
                "name": "Surat Permohonan dan Jaminan",
                "description": "Official letter of application and guarantee from an Indonesian sponsor (template provided)",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": False,
                "is_in_required_documents": True,
            },
            {
                "name": "Invitation Letter",
                "description": "Invitation letter from event organizer or host for special-purpose visas",
                "has_ocr_check": False,
                "has_expiration_date": False,
                "has_doc_number": False,
                "has_file": True,
                "has_details": True,
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
                "is_in_required_documents": True,
            },
        ]

        for doc_type in document_types:
            obj, created = DocumentType.objects.get_or_create(name=doc_type["name"], defaults=doc_type)
            if created:
                self.stdout.write(self.style.SUCCESS(f"Created document type: {doc_type['name']}"))
            else:
                updated = False
                for key, value in doc_type.items():
                    if key != "name" and getattr(obj, key) != value:
                        setattr(obj, key, value)
                        updated = True
                if updated:
                    obj.save()
                    self.stdout.write(self.style.SUCCESS(f"Updated document type: {doc_type['name']}"))
                else:
                    self.stdout.write(
                        self.style.WARNING(f"Document type '{doc_type['name']}' already exists and is up to date.")
                    )

        self.stdout.write(self.style.SUCCESS("Finished populating DocumentType table"))
