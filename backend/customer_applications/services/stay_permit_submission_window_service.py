from __future__ import annotations

from dataclasses import dataclass
from datetime import date, timedelta

from django.core.exceptions import ValidationError

from customer_applications.models.document import Document
from products.models.document_type import DocumentType
from products.models.product import Product


@dataclass(frozen=True)
class StayPermitSubmissionWindow:
    first_date: date
    last_date: date


class StayPermitSubmissionWindowService:
    """Compute and validate submission windows derived from stay permit expirations."""

    @staticmethod
    def _split_document_names(value: str | None) -> set[str]:
        if not value:
            return set()
        return {name.strip() for name in value.split(",") if name and name.strip()}

    def _stay_permit_document_names_for_product(self, product: Product | None) -> set[str]:
        if not product or product.product_type != "visa":
            return set()

        configured_doc_names = self._split_document_names(product.required_documents) | self._split_document_names(
            product.optional_documents
        )
        if not configured_doc_names:
            return set()

        return set(
            DocumentType.objects.filter(name__in=configured_doc_names, is_stay_permit=True).values_list(
                "name",
                flat=True,
            )
        )

    def get_submission_window(
        self,
        *,
        product: Product | None,
        application=None,
    ) -> StayPermitSubmissionWindow | None:
        stay_permit_doc_names = self._stay_permit_document_names_for_product(product)
        if not stay_permit_doc_names or application is None:
            return None

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
                        "Application date must be between "
                        f"{window.first_date.isoformat()} and {window.last_date.isoformat()} "
                        "(inclusive) based on stay permit expiration."
                    ]
                }
            )
