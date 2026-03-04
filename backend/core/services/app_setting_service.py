from __future__ import annotations

import json
import logging
import re
from collections.abc import Iterable
from typing import Any

from core.models import AppSetting


class AppSettingScope:
    BACKEND = "backend"
    FRONTEND = "frontend"
    BOTH = "both"


_INT_PATTERN = re.compile(r"^-?\d+$")
_FLOAT_PATTERN = re.compile(r"^-?\d+\.\d+$")
logger = logging.getLogger(__name__)


class AppSettingService:
    @staticmethod
    def _resolve_updated_by_id(updated_by: Any) -> Any:
        if updated_by is None:
            return None
        for attr in ("pk", "id"):
            value = getattr(updated_by, attr, None)
            if value not in (None, ""):
                return value
        if isinstance(updated_by, (int, str)):
            return updated_by
        return None

    @staticmethod
    def _is_runtime_override(record: Any) -> bool:
        return getattr(record, "updated_by_id", None) is not None

    @staticmethod
    def _model_available() -> bool:
        return AppSetting is not None

    @classmethod
    def get_raw(cls, name: str, default: Any = None, *, require_override: bool = False) -> Any:
        if not cls._model_available():
            return default
        try:
            if require_override:
                record = AppSetting.objects.filter(name=name).only("value", "updated_by_id").first()
            else:
                record = AppSetting.objects.filter(name=name).only("value").first()
        except Exception:
            return default
        if record is None:
            return default
        if require_override and not cls._is_runtime_override(record):
            return default
        return record.value

    @classmethod
    def set_raw(
        cls,
        *,
        name: str,
        value: str,
        scope: str = AppSettingScope.BACKEND,
        description: str = "",
        updated_by=None,
    ) -> None:
        if not cls._model_available():
            return
        try:
            AppSetting.objects.update_or_create(
                name=name,
                defaults={
                    "value": value,
                    "scope": scope,
                    "description": description or "",
                    # Persist FK by id to support token-like auth users without a concrete model instance.
                    "updated_by_id": cls._resolve_updated_by_id(updated_by),
                },
            )
        except Exception:
            logger.exception("Failed to persist AppSetting '%s'", name)
            return

    @classmethod
    def delete_raw(cls, name: str) -> None:
        if not cls._model_available():
            return
        try:
            AppSetting.objects.filter(name=name).delete()
        except Exception:
            logger.exception("Failed to delete AppSetting '%s'", name)
            return

    @classmethod
    def get_scoped_values(cls, scopes: Iterable[str]) -> dict[str, str]:
        if not cls._model_available():
            return {}
        try:
            rows = AppSetting.objects.filter(scope__in=list(scopes)).values("name", "value")
        except Exception:
            return {}
        return {str(row["name"]): str(row["value"]) for row in rows}

    @staticmethod
    def parse_bool(value: Any, default: bool = False) -> bool:
        if isinstance(value, bool):
            return value
        if value is None:
            return default
        normalized = str(value).strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
        return default

    @staticmethod
    def parse_int(value: Any, default: int = 0) -> int:
        try:
            return int(str(value).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def parse_float(value: Any, default: float = 0.0) -> float:
        try:
            return float(str(value).strip())
        except (TypeError, ValueError):
            return default

    @staticmethod
    def parse_list(value: Any, default: list[str] | None = None) -> list[str]:
        if default is None:
            default = []
        if value is None:
            return list(default)
        if isinstance(value, (list, tuple)):
            return [str(item).strip() for item in value if str(item).strip()]
        return [part.strip() for part in str(value).split(",") if part.strip()]

    @staticmethod
    def parse_json_like(value: Any) -> Any:
        if value is None:
            return None
        if isinstance(value, (bool, int, float, list, dict)):
            return value
        text = str(value).strip()
        lowered = text.lower()
        if lowered in {"true", "false"}:
            return lowered == "true"
        if _INT_PATTERN.fullmatch(text):
            try:
                return int(text)
            except (TypeError, ValueError):
                return text
        if _FLOAT_PATTERN.fullmatch(text):
            try:
                return float(text)
            except (TypeError, ValueError):
                return text
        if text.startswith("{") or text.startswith("["):
            try:
                return json.loads(text)
            except json.JSONDecodeError:
                return text
        return text
