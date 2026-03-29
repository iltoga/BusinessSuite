"""
FILE_ROLE: Service-layer logic for the customer applications app.

KEY_COMPONENTS:
- StayPermitSubmissionWindowService: Service class.

INTERACTIONS:
- Depends on: nearby Django models, services, serializers, and the app packages imported by this module.

AI_GUIDELINES:
- Keep the module focused on its narrow layer boundary and avoid moving cross-cutting workflow code here.
- Preserve the existing API/model contract because other modules import these symbols directly.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from customer_applications.models.document import Document
from django.core.exceptions import ValidationError
from products.models.document_type import DocumentType
from products.models.product import Product


@dataclass(frozen=True)
class StayPermitSubmissionWindow:
    first_date: date
    last_date: date


class StayPermitSubmissionWindowService:
    """Compute and validate submission windows derived from stay permit expirations."""

    def _prefetched_documents(self, application) -> list[Document] | None:
        prefetched = getattr(application, "_prefetched_objects_cache", None) or {}
        documents = prefetched.get("documents")
        return list(documents) if documents is not None else None

    @staticmethod
    def _split_document_names(value: str | None) -> set[str]:
        if not value:
            return set()
        return {name.strip() for name in value.split(",") if name and name.strip()}

    def stay_permit_document_names_for_product(self, product: Product | None) -> set[str]:
        if not product or not getattr(product, "product_category", None):
            return set()
        if product.product_category.product_type != "visa":
            return set()

        cached = getattr(product, "_stay_permit_document_names_cache", None)
        if cached is not None:
            return set(cached)

        configured_doc_names = self._split_document_names(product.required_documents) | self._split_document_names(
            product.optional_documents
        )
        if not configured_doc_names:
            return set()

        stay_permit_names = set(
            DocumentType.objects.filter(name__in=configured_doc_names, is_stay_permit=True).values_list(
                "name",
                flat=True,
            )
        )
        product._stay_permit_document_names_cache = tuple(sorted(stay_permit_names))
        return stay_permit_names

    def product_requires_submission_window(self, product: Product | None) -> bool:
        return bool(self.stay_permit_document_names_for_product(product))

    def get_submission_window(
        self,
        *,
        product: Product | None,
        application=None,
    ) -> StayPermitSubmissionWindow | None:
        stay_permit_doc_names = self.stay_permit_document_names_for_product(product)
        if not stay_permit_doc_names or application is None:
            return None

        prefetched_documents = self._prefetched_documents(application)
        if prefetched_documents is not None:
            matching_documents = [
                document
                for document in prefetched_documents
                if getattr(document, "expiration_date", None)
                and getattr(document, "doc_type", None)
                and document.doc_type.is_stay_permit
                and document.doc_type.name in stay_permit_doc_names
            ]
            stay_permit_document = (
                min(matching_documents, key=lambda document: document.expiration_date) if matching_documents else None
            )
        else:
            # When multiple stay permit documents exist, use the earliest expiration date.
            stay_permit_document = (
                Document.objects.filter(
                    doc_application=application,
                    doc_type__name__in=stay_permit_doc_names,
                    doc_type__is_stay_permit=True,
                    expiration_date__isnull=False,
                )
                .order_by("expiration_date")
                .first()
            )
        if not stay_permit_document or not stay_permit_document.expiration_date:
            return None

        last_date = stay_permit_document.expiration_date
        window_days = int(product.application_window_days or 0) if product else 0
        first_date = last_date - timedelta(days=max(window_days, 0))
        return StayPermitSubmissionWindow(first_date=first_date, last_date=last_date)

    def validate_doc_date(
        self,
        *,
        product: Product | None,
        doc_date: date | None,
        application=None,
    ) -> None:
        if not doc_date:
            return

        window = self.get_submission_window(product=product, application=application)
        if window is None:
            return

        if doc_date < window.first_date or doc_date > window.last_date:
            raise ValidationError(
                {
                    "doc_date": [
                        "Application submission date must be between "
                        f"{window.first_date.isoformat()} and {window.last_date.isoformat()} "
                        "(inclusive) based on stay permit expiration."
                    ]
                }
            )

    def resolve_submission_date(
        self,
        *,
        product: Product | None,
        application=None,
        preferred_date: date | None = None,
    ) -> date | None:
        """Return the submission date that should drive step 1 for stay-permit-gated products.

        If no submission window exists yet, return ``None``.
        If a preferred/current date is inside the window, keep it.
        Otherwise, normalize to the first day of the submission window.
        """
        window = self.get_submission_window(product=product, application=application)
        if window is None:
            return None

        candidate = preferred_date or getattr(application, "doc_date", None)
        if candidate and window.first_date <= candidate <= window.last_date:
            return candidate
        return window.first_date
