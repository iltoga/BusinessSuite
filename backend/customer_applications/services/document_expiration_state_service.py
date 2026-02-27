from __future__ import annotations

from dataclasses import dataclass

from django.utils import timezone


@dataclass(frozen=True)
class DocumentExpirationState:
    state: str
    reason: str | None
    threshold_days: int

    @property
    def is_invalid(self) -> bool:
        return self.state in {"expired", "expiring"}


class DocumentExpirationStateService:
    STATE_OK = "ok"
    STATE_EXPIRING = "expiring"
    STATE_EXPIRED = "expired"

    def evaluate(self, document) -> DocumentExpirationState:
        expiration_date = getattr(document, "expiration_date", None)
        doc_type = getattr(document, "doc_type", None)
        has_expiration = bool(getattr(doc_type, "has_expiration_date", False))
        threshold_days = self._threshold_days(doc_type)

        if not has_expiration or not expiration_date:
            return DocumentExpirationState(state=self.STATE_OK, reason=None, threshold_days=threshold_days)

        today = timezone.localdate()
        if expiration_date < today:
            return DocumentExpirationState(
                state=self.STATE_EXPIRED,
                reason=f"Document expired on {expiration_date.isoformat()}.",
                threshold_days=threshold_days,
            )

        if threshold_days > 0:
            threshold_date = today + timezone.timedelta(days=threshold_days)
            if expiration_date <= threshold_date:
                return DocumentExpirationState(
                    state=self.STATE_EXPIRING,
                    reason=(
                        "Document is expiring soon: expiration date "
                        f"{expiration_date.isoformat()} is within {threshold_days} days."
                    ),
                    threshold_days=threshold_days,
                )

        return DocumentExpirationState(state=self.STATE_OK, reason=None, threshold_days=threshold_days)

    @staticmethod
    def _threshold_days(doc_type) -> int:
        raw = getattr(doc_type, "expiring_threshold_days", 0)
        try:
            value = int(raw or 0)
        except (TypeError, ValueError):
            return 0
        return max(value, 0)
