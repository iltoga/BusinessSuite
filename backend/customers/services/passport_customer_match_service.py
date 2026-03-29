"""Service for matching passport data to existing customer records."""

from __future__ import annotations

import logging
import re
from typing import Any

from customers.models import Customer
from django.contrib.postgres.search import TrigramSimilarity
from django.db.models import ExpressionWrapper, F, FloatField, Q, Value
from django.db.models.functions import Coalesce, Greatest

logger = logging.getLogger(__name__)


class PassportCustomerMatchService:
    """Resolve passport-check extracted data against existing customers."""

    def __init__(self, similarity_threshold: float = 0.35, max_similar_matches: int = 10):
        self.similarity_threshold = similarity_threshold
        self.max_similar_matches = max_similar_matches

    def match(self, passport_data: dict[str, Any] | None) -> dict[str, Any]:
        data = passport_data or {}
        first_name = self._normalize_name(data.get("first_name"))
        last_name = self._normalize_name(data.get("last_name"))
        passport_number = self._normalize_passport_number(data.get("passport_number"))

        if passport_number:
            passport_match = (
                Customer.objects.select_related("nationality").filter(passport_number__iexact=passport_number).first()
            )
            if passport_match:
                return {
                    "status": "passport_found",
                    "message": "A customer with this passport number already exists.",
                    "passport_number": passport_number,
                    "exact_matches": [self._serialize_customer(passport_match, match_kind="passport_exact")],
                    "similar_matches": [],
                    "recommended_action": "update_customer",
                }

        if not first_name or not last_name:
            return {
                "status": "insufficient_data",
                "message": "Not enough extracted data to search existing customers.",
                "passport_number": passport_number,
                "exact_matches": [],
                "similar_matches": [],
                "recommended_action": "none",
            }

        exact_filter = Q(first_name__iexact=first_name, last_name__iexact=last_name) | Q(
            first_name__iexact=last_name,
            last_name__iexact=first_name,
        )
        exact_matches = list(
            Customer.objects.select_related("nationality").filter(exact_filter).order_by("-updated_at")
        )
        if exact_matches:
            serialized_exact = [
                self._serialize_customer(customer, match_kind="name_exact") for customer in exact_matches
            ]
            return {
                "status": "exact_name_found",
                "message": "Customer name match found.",
                "passport_number": passport_number,
                "exact_matches": serialized_exact,
                "similar_matches": [],
                "recommended_action": "update_customer" if len(serialized_exact) == 1 else "choose_customer",
            }

        try:
            similar_matches = self._find_similar_matches(first_name=first_name, last_name=last_name)
        except Exception as exc:
            logger.warning("Fuzzy customer matching failed; falling back to no similar results: %s", exc)
            similar_matches = []
        if similar_matches:
            return {
                "status": "similar_name_found",
                "message": "Similar customer names were found.",
                "passport_number": passport_number,
                "exact_matches": [],
                "similar_matches": similar_matches,
                "recommended_action": "choose_customer",
            }

        return {
            "status": "no_match",
            "message": "No customer found with this passport number or similar name.",
            "passport_number": passport_number,
            "exact_matches": [],
            "similar_matches": [],
            "recommended_action": "create_customer",
        }

    def _find_similar_matches(self, first_name: str, last_name: str) -> list[dict[str, Any]]:
        direct_score = ExpressionWrapper(
            (
                Coalesce(TrigramSimilarity("first_name", first_name), Value(0.0))
                + Coalesce(TrigramSimilarity("last_name", last_name), Value(0.0))
            )
            / Value(2.0),
            output_field=FloatField(),
        )
        reverse_score = ExpressionWrapper(
            (
                Coalesce(TrigramSimilarity("first_name", last_name), Value(0.0))
                + Coalesce(TrigramSimilarity("last_name", first_name), Value(0.0))
            )
            / Value(2.0),
            output_field=FloatField(),
        )

        exact_filter = Q(first_name__iexact=first_name, last_name__iexact=last_name) | Q(
            first_name__iexact=last_name,
            last_name__iexact=first_name,
        )

        queryset = (
            Customer.objects.select_related("nationality")
            .exclude(exact_filter)
            .annotate(
                direct_similarity=direct_score,
                reverse_similarity=reverse_score,
            )
            .annotate(
                similarity=Greatest(F("direct_similarity"), F("reverse_similarity")),
            )
            .filter(similarity__gte=self.similarity_threshold)
            .order_by("-similarity", "-updated_at")[: self.max_similar_matches]
        )

        return [
            self._serialize_customer(
                customer,
                match_kind="name_similar",
                similarity=getattr(customer, "similarity", None),
            )
            for customer in queryset
        ]

    def _serialize_customer(
        self,
        customer: Customer,
        *,
        match_kind: str,
        similarity: float | None = None,
    ) -> dict[str, Any]:
        nationality_code = customer.nationality.alpha3_code if customer.nationality else None
        nationality_name = (
            (customer.nationality.country_idn or customer.nationality.country) if customer.nationality else None
        )

        if customer.passport_number:
            passport_status = "present"
        else:
            passport_status = "missing"

        return {
            "id": customer.id,
            "first_name": customer.first_name,
            "last_name": customer.last_name,
            "full_name": customer.full_name,
            "passport_number": customer.passport_number,
            "passport_issue_date": customer.passport_issue_date.isoformat() if customer.passport_issue_date else None,
            "passport_expiration_date": (
                customer.passport_expiration_date.isoformat() if customer.passport_expiration_date else None
            ),
            "nationality_code": nationality_code,
            "nationality_name": nationality_name,
            "match_kind": match_kind,
            "passport_status": passport_status,
            "similarity": round(float(similarity), 4) if similarity is not None else None,
        }

    @staticmethod
    def _normalize_name(value: Any) -> str:
        if value is None:
            return ""
        normalized = str(value).replace("<", " ")
        normalized = re.sub(r"\s+", " ", normalized).strip()
        return normalized

    @staticmethod
    def _normalize_passport_number(value: Any) -> str:
        if value is None:
            return ""
        normalized = re.sub(r"\s+", "", str(value)).strip().upper()
        return normalized
