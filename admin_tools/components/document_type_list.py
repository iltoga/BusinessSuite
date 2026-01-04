from django.db.models import ProtectedError

from core.components.unicorn_search_list_view import UnicornSearchListView
from products.models.document_type import DocumentType


class DocumentTypeListView(UnicornSearchListView):
    model = DocumentType
    model_search_method = "search_document_types"
    # Show 25 items per page by default (increase from the base 10)
    items_per_page = 25

    # Form fields
    document_type_id = None
    name = ""
    description = ""
    has_ocr_check = False
    has_expiration_date = False
    has_doc_number = False
    has_file = False
    has_details = False
    validation_rule_regex = ""
    is_in_required_documents = False

    error_message = ""
    success_message = ""

    def updated_search_input(self, value):
        self.page = 1
        self.search()

    def clear_search(self):
        self.search_input = ""
        self.page = 1
        self.search()

    def edit(self, pk):
        dt = DocumentType.objects.get(pk=pk)
        self.document_type_id = dt.pk
        self.name = dt.name
        self.description = dt.description
        self.has_ocr_check = dt.has_ocr_check
        self.has_expiration_date = dt.has_expiration_date
        self.has_doc_number = dt.has_doc_number
        self.has_file = dt.has_file
        self.has_details = dt.has_details
        self.validation_rule_regex = dt.validation_rule_regex
        self.is_in_required_documents = dt.is_in_required_documents
        self.error_message = ""
        self.success_message = ""
        self.call("openModal")

    def create_new(self):
        self.create_new_fields()
        self.error_message = ""
        self.success_message = ""
        self.call("openModal")

    def save_document_type(self):
        if not self.name:
            self.error_message = "Name is required."
            return

        try:
            if self.document_type_id:
                dt = DocumentType.objects.get(pk=self.document_type_id)
            else:
                dt = DocumentType()

            dt.name = self.name
            dt.description = self.description
            dt.has_ocr_check = self.has_ocr_check
            dt.has_expiration_date = self.has_expiration_date
            dt.has_doc_number = self.has_doc_number
            dt.has_file = self.has_file
            dt.has_details = self.has_details
            dt.validation_rule_regex = self.validation_rule_regex
            dt.is_in_required_documents = self.is_in_required_documents

            dt.save()
            self.success_message = f"Document type '{dt.name}' saved successfully."
            self.document_type_id = None  # Reset form
            self.create_new_fields()  # Clear fields
            self.load_items()
            self.call("closeModal")
        except Exception as e:
            self.error_message = str(e)

    def create_new_fields(self):
        """Internal method to clear fields without triggering openModal."""
        self.document_type_id = None
        self.name = ""
        self.description = ""
        self.has_ocr_check = False
        self.has_expiration_date = False
        self.has_doc_number = False
        self.has_file = False
        self.has_details = False
        self.validation_rule_regex = ""
        self.is_in_required_documents = False

    def delete_document_type(self, pk):
        try:
            dt = DocumentType.objects.get(pk=pk)

            # Check if any product uses this document type (comma separated strings)
            from django.db.models import Q

            from products.models.product import Product

            # We check for the name surrounded by commas or at the beginning/end
            # This is a bit hacky but works for comma-separated strings
            if Product.objects.filter(
                Q(required_documents__icontains=dt.name) | Q(optional_documents__icontains=dt.name)
            ).exists():
                # Double check to avoid partial matches if names are similar
                products = Product.objects.filter(
                    Q(required_documents__icontains=dt.name) | Q(optional_documents__icontains=dt.name)
                )
                found = False
                for p in products:
                    req = [d.strip() for d in p.required_documents.split(",") if d.strip()]
                    opt = [d.strip() for d in p.optional_documents.split(",") if d.strip()]
                    if dt.name in req or dt.name in opt:
                        found = True
                        break
                if found:
                    self.error_message = f"Cannot delete '{dt.name}' because it is used in one or more products."
                    return

            dt.delete()
            self.success_message = "Document type deleted successfully."
            self.load_items()
        except ProtectedError:
            self.error_message = "Cannot delete this document type because it is linked to existing documents."
        except Exception as e:
            self.error_message = str(e)

    def clear_messages(self):
        self.error_message = ""
        self.success_message = ""
