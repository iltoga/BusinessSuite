from django.test import TestCase

from products.models import DocumentType, Product


class ProductDeprecatedSyncTests(TestCase):
    def test_sync_deprecated_status_clears_when_no_deprecated_document_types(self):
        deprecated_doc = DocumentType.objects.create(name="Legacy Doc", deprecated=True)
        active_doc = DocumentType.objects.create(name="Active Doc", deprecated=False)

        product = Product.objects.create(
            code="PRD-DEP-1",
            name="Deprecated Sync Product",
            required_documents=deprecated_doc.name,
        )
        self.assertTrue(product.deprecated)

        product.required_documents = active_doc.name
        product.optional_documents = ""
        product.save()
        product.refresh_from_db()

        self.assertFalse(product.deprecated)
