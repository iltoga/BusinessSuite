from django.db import models


class DocumentTypeManager(models.Manager):
    def search_document_types(self, query):
        return self.filter(models.Q(name__icontains=query) | models.Q(description__icontains=query))


class DocumentType(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.CharField(max_length=500, blank=True)
    deprecated = models.BooleanField(default=False, db_index=True)
    ai_validation = models.BooleanField(default=True)
    has_expiration_date = models.BooleanField(default=False)
    has_doc_number = models.BooleanField(default=False)
    has_file = models.BooleanField(default=False)
    has_details = models.BooleanField(default=False)
    validation_rule_regex = models.CharField(max_length=500, blank=True)
    validation_rule_ai_positive = models.TextField(blank=True)
    validation_rule_ai_negative = models.TextField(blank=True)
    is_in_required_documents = models.BooleanField(default=False)

    objects = DocumentTypeManager()

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        # This method is used to provide custom model validation,
        # and to modify attributes on your model if desired.
        if self.ai_validation and not self.has_file:
            self.has_file = True

    def get_related_products(self):
        from products.models.product import Product

        return Product.objects.db_manager(self._state.db).filter_by_document_type_name(self.name)

    def save(self, *args, **kwargs):
        self.full_clean()
        super(DocumentType, self).save(*args, **kwargs)
