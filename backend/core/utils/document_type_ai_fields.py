import json
from dataclasses import dataclass


@dataclass(frozen=True)
class StructuredOutputField:
    field_name: str
    description: str


def parse_structured_output_fields(raw_value: str | None) -> list[StructuredOutputField]:
    if not raw_value or not str(raw_value).strip():
        return []

    try:
        payload = json.loads(raw_value)
    except (TypeError, ValueError, json.JSONDecodeError):
        return []

    if not isinstance(payload, list):
        return []

    normalized: list[StructuredOutputField] = []
    seen_names: set[str] = set()
    for item in payload:
        if not isinstance(item, dict):
            continue

        name_raw = item.get("field_name", item.get("fieldName"))
        description_raw = item.get("description")
        field_name = str(name_raw or "").strip()
        description = str(description_raw or "").strip()
        if not field_name or field_name in seen_names:
            continue

        seen_names.add(field_name)
        normalized.append(StructuredOutputField(field_name=field_name, description=description))

    return normalized


def format_fields_for_prompt(fields: list[StructuredOutputField]) -> str:
    lines = []
    for item in fields:
        if item.description:
            lines.append(f"- {item.field_name}: {item.description}")
        else:
            lines.append(f"- {item.field_name}")
    return "\n".join(lines)


def build_strict_structured_schema(fields: list[StructuredOutputField]) -> dict:
    properties: dict[str, dict] = {}
    required: list[str] = []

    for item in fields:
        properties[item.field_name] = {
            "type": ["string", "null"],
            "description": item.description
            or f"Extracted value for field '{item.field_name}'. Return null when unavailable.",
        }
        required.append(item.field_name)

    return {
        "type": "object",
        "properties": properties,
        "required": required,
        "additionalProperties": False,
    }
