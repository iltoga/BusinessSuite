from django.core.exceptions import ValidationError
from django.db import models


class DocumentType(models.Model):
    name = models.CharField(max_length=50, unique=True, db_index=True)
    description = models.CharField(max_length=500, blank=True)
    has_ocr_check = models.BooleanField(default=False)
    has_expiration_date = models.BooleanField(default=False)
    has_doc_number = models.BooleanField(default=False)
    has_file = models.BooleanField(default=False)
    has_details = models.BooleanField(default=False)
    validation_rule_regex = models.CharField(max_length=500, blank=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name

    def clean(self):
        # This method is used to provide custom model validation,
        # and to modify attributes on your model if desired.
        if self.has_ocr_check and not self.has_file:
            raise ValidationError("If has_ocr_check is True, has_file should also be True.")

    def save(self, *args, **kwargs):
        self.full_clean()
        return super(DocumentType, self).save(*args, **kwargs)
