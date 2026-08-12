"""Preflight validation for the exact strict schema CrewAI sends to OpenAI."""
from __future__ import annotations

from typing import Any


class StructuredOutputSchemaError(ValueError):
    """A permanent local configuration error; retrying would waste model calls."""


def validate_strict_schema(schema: dict[str, Any], path: str = "$") -> None:
    """Ensure each JSON object has internally consistent OpenAI strict fields."""
    if not isinstance(schema, dict):
        return
    if schema.get("type") == "object":
        properties = schema.get("properties")
        required = schema.get("required")
        if not isinstance(properties, dict):
            raise StructuredOutputSchemaError(f"{path}: object is missing a properties object.")
        if not isinstance(required, list):
            raise StructuredOutputSchemaError(f"{path}: object is missing a required array.")
        extras = set(required) - set(properties)
        if extras:
            raise StructuredOutputSchemaError(f"{path}: required keys absent from properties: {sorted(extras)}.")
        if schema.get("additionalProperties") is not False:
            raise StructuredOutputSchemaError(f"{path}: strict schema must set additionalProperties to false.")
    for key, value in schema.items():
        if isinstance(value, dict):
            validate_strict_schema(value, f"{path}.{key}")
        elif isinstance(value, list):
            for index, item in enumerate(value):
                if isinstance(item, dict):
                    validate_strict_schema(item, f"{path}.{key}[{index}]")


def crewai_strict_schema(model: type[Any]) -> dict[str, Any]:
    """Build then validate CrewAI's transformed strict schema before a network call."""
    try:
        from crewai.utilities.pydantic_schema_utils import generate_model_description
    except ImportError as exc:  # pragma: no cover
        raise StructuredOutputSchemaError("CrewAI is unavailable for structured-output schema validation.") from exc
    schema = generate_model_description(model)["json_schema"]["schema"]
    validate_strict_schema(schema)
    return schema
