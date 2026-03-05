from __future__ import annotations

import json
import logging
import os
import re
from collections.abc import Iterable
from typing import Any

from core.models import AppSetting
from django.conf import settings
from django.core.cache import cache


class AppSettingScope:
    BACKEND = "backend"
    FRONTEND = "frontend"
    BOTH = "both"


_INT_PATTERN = re.compile(r"^-?\d+$")
_FLOAT_PATTERN = re.compile(r"^-?\d+\.\d+$")
logger = logging.getLogger(__name__)


class AppSettingService:
    _CACHE_ALL_ROWS_KEY = "app_settings:rows:v1"
    _RUNTIME_OVERRIDE_MARKER = "__runtime_override__"

    @staticmethod
    def _cache_enabled() -> bool:
        return not bool(getattr(settings, "TESTING", False))

    @classmethod
    def invalidate_cache(cls) -> None:
        if not cls._cache_enabled():
            return
        try:
            cache.delete(cls._CACHE_ALL_ROWS_KEY)
        except Exception:
            return

    @classmethod
    def _load_all_rows(cls) -> dict[str, dict[str, Any]]:
        if cls._cache_enabled():
            try:
                cached = cache.get(cls._CACHE_ALL_ROWS_KEY)
                if isinstance(cached, dict):
                    return cached
            except Exception:
                cached = None

        if not cls._model_available():
            return {}

        try:
            rows = list(
                AppSetting.objects.all().values(
                    "name", "value", "updated_by_id", "scope", "description", "created_at", "updated_at"
                )
            )
        except Exception:
            return {}

        mapped = {
            str(row["name"]): {
                "value": row.get("value"),
                "updated_by_id": row.get("updated_by_id"),
                "scope": row.get("scope"),
                "description": row.get("description"),
                "created_at": row.get("created_at"),
                "updated_at": row.get("updated_at"),
            }
            for row in rows
        }
        if cls._cache_enabled():
            try:
                cache.set(cls._CACHE_ALL_ROWS_KEY, mapped, timeout=None)
            except Exception:
                return mapped
        return mapped

    @classmethod
    def get_effective_raw(cls, name: str, hardcoded_default: Any = None) -> Any:
        """Resolve setting precedence: hardcoded < django settings < env < DB AppSetting."""
        value = hardcoded_default

        if hasattr(settings, name):
            configured = getattr(settings, name)
            if configured is not None:
                value = configured

        env_value = os.getenv(name)
        if env_value is not None and str(env_value).strip() != "":
            value = env_value

        db_value = cls.get_raw(name, default=None, require_override=True)
        if db_value is not None and str(db_value).strip() != "":
            value = db_value

        return value

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

    @classmethod
    def _is_runtime_override(cls, record: Any) -> bool:
        if record is None:
            return False
        updated_by_id = record.get("updated_by_id") if isinstance(record, dict) else getattr(record, "updated_by_id", None)
        if updated_by_id is not None:
            return True
        description = record.get("description") if isinstance(record, dict) else getattr(record, "description", "")
        return cls._RUNTIME_OVERRIDE_MARKER in str(description or "")

    @staticmethod
    def _model_available() -> bool:
        return AppSetting is not None

    @classmethod
    def get_raw(cls, name: str, default: Any = None, *, require_override: bool = False) -> Any:
        row = cls._load_all_rows().get(name)
        if row is None:
            return default
        if require_override and not cls._is_runtime_override(row):
            return default
        return row.get("value")

    @classmethod
    def set_raw(
        cls,
        *,
        name: str,
        value: str,
        scope: str = AppSettingScope.BACKEND,
        description: str = "",
        updated_by=None,
        force_override: bool = False,
    ) -> None:
        if not cls._model_available():
            return
        try:
            final_description = description or ""
            if force_override and cls._RUNTIME_OVERRIDE_MARKER not in final_description:
                final_description = f"{final_description}\n{cls._RUNTIME_OVERRIDE_MARKER}".strip()
            AppSetting.objects.update_or_create(
                name=name,
                defaults={
                    "value": value,
                    "scope": scope,
                    "description": final_description,
                    # Persist FK by id to support token-like auth users without a concrete model instance.
                    "updated_by_id": cls._resolve_updated_by_id(updated_by),
                },
            )
            cls.invalidate_cache()
        except Exception:
            logger.exception("Failed to persist AppSetting '%s'", name)
            return

    @classmethod
    def delete_raw(cls, name: str) -> None:
        if not cls._model_available():
            return
        try:
            AppSetting.objects.filter(name=name).delete()
            cls.invalidate_cache()
        except Exception:
            logger.exception("Failed to delete AppSetting '%s'", name)
            return

    @classmethod
    def get_scoped_values(cls, scopes: Iterable[str]) -> dict[str, str]:
        allowed_scopes = set(scopes)
        rows = cls._load_all_rows()
        return {
            str(name): str(payload.get("value") or "")
            for name, payload in rows.items()
            if str(payload.get("scope") or "") in allowed_scopes
        }

    @classmethod
    def get_metadata(
        cls,
        name: str,
        *,
        hardcoded_default: Any = None,
        fallback_scope: str = AppSettingScope.BACKEND,
        fallback_description: str = "",
        effective_value: Any = None,
    ) -> dict[str, Any]:
        row = cls._load_all_rows().get(name)
        runtime_override = cls._is_runtime_override(row)

        if effective_value is None:
            effective_value = cls.get_effective_raw(name, hardcoded_default)

        env_value = os.getenv(name)
        source = "hardcoded"
        if runtime_override:
            source = "database"
        elif env_value is not None and str(env_value).strip() != "":
            source = "env"
        elif hasattr(settings, name):
            source = "django"

        return {
            "name": name,
            "value": row.get("value") if row else None,
            "effectiveValue": effective_value,
            "defaultValue": hardcoded_default,
            "scope": row.get("scope") if row else fallback_scope,
            "description": row.get("description") if row else fallback_description,
            "source": source,
            "updatedAt": row.get("updated_at") if row else None,
            "updatedById": row.get("updated_by_id") if row else None,
            "isOverridden": bool(runtime_override),
        }

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
