"""
FILE_ROLE: Primary data models for the core app.

KEY_COMPONENTS:
- CountryCode: Module symbol.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on model definitions and local invariants.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from django.db import models


# Add Model Manager class here
class CountryCodeManager(models.Manager):
    def search_country_codes(self, query):
        return self.filter(
            models.Q(name__icontains=query)
            | models.Q(date__icontains=query)
            | models.Q(country__icontains=query)
            | models.Q(description__icontains=query)
        )

    def get_country_code_by_alpha3_code(self, alpha3_code):
        return self.filter(alpha3_code=alpha3_code).first()


class CountryCode(models.Model):
    country = models.CharField(max_length=100, unique=True, blank=False, null=False, db_index=True)
    # Indonesian/official government country name label
    country_idn = models.CharField(max_length=128, blank=True, null=True, db_index=True)
    alpha2_code = models.CharField(max_length=2, unique=True, blank=False, null=False, db_index=True)
    alpha3_code = models.CharField(primary_key=True, max_length=3, unique=True, blank=False, null=False)
    numeric_code = models.CharField(max_length=3, unique=True, blank=False, null=False, db_index=True)
    objects = CountryCodeManager()

    class Meta:
        ordering = ["country"]

    def __str__(self):
        return self.country + " (" + self.alpha3_code + ")"
