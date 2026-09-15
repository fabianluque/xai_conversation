"""Convert Home Assistant LLM tool schemas for the xAI client API."""

from __future__ import annotations

import json
from typing import Any

from probatio import UNSUPPORTED, to_openapi


def sanitize_schema(value: Any) -> Any:
    """
    Make OpenAPI schemas JSON-serializable for the xAI SDK.

    Home Assistant's ``probatio.to_openapi`` / selector serializers can embed
    ``UNSUPPORTED`` markers that are not JSON serializable. The xAI SDK
    ``json.dumps``es tool parameters, so those markers must be removed.
    """
    if value is UNSUPPORTED:
        return {}
    if isinstance(value, dict):
        return {
            key: sanitized
            for key, item in value.items()
            if (sanitized := sanitize_schema(item)) is not None
        }
    if isinstance(value, list):
        return [sanitize_schema(item) for item in value]
    if isinstance(value, (str, int, float, bool)) or value is None:
        return value
    try:
        json.dumps(value)
    except TypeError:
        return {}
    return value


def ensure_object_tool_schema(schema: Any) -> dict[str, Any]:
    """
    Normalize a tool parameter schema to a JSON object root.

    xAI rejects client tools whose parameters root is an ``anyOf``/``oneOf``
    union (for example Assist's ``HassStartTimer`` ``Required(Any(...))``
    slot schema). Prefer an object branch when present; otherwise drop
    composition keywords at the root, matching Home Assistant's OpenAI
    conversation integration.
    """
    schema = sanitize_schema(schema)
    if not isinstance(schema, dict):
        return {"type": "object", "properties": {}}

    for union_key in ("anyOf", "oneOf"):
        if union_key not in schema:
            continue
        branches = [b for b in (schema.get(union_key) or []) if isinstance(b, dict)]
        object_branches = [
            branch
            for branch in branches
            if branch.get("type") == "object" or "properties" in branch
        ]
        if object_branches:
            chosen = dict(object_branches[0])
            for key, value in schema.items():
                if key not in {"anyOf", "oneOf", "allOf", "not"}:
                    chosen.setdefault(key, value)
            schema = chosen
        else:
            # Composition-only constraints (e.g. required-one-of fields) —
            # keep the object shape and drop the union keys.
            schema = {
                key: value
                for key, value in schema.items()
                if key not in {"anyOf", "oneOf", "allOf", "not"}
            }
        break
    else:
        unsupported_keys = {"oneOf", "anyOf", "allOf", "not"}
        if unsupported_keys.intersection(schema):
            schema = {
                key: value
                for key, value in schema.items()
                if key not in unsupported_keys
            }

    if "properties" in schema or schema.get("type") == "object":
        schema.setdefault("type", "object")
        schema.setdefault("properties", {})
        return schema

    # Last resort: wrap non-object schemas so xAI accepts the tool.
    return {
        "type": "object",
        "properties": {"value": schema} if schema else {},
        "additionalProperties": True,
    }


def format_tool_parameters(
    parameters: Any, *, custom_serializer: Any = None
) -> dict[str, Any]:
    """Convert an HA LLM / probatio schema into xAI-compatible tool parameters."""
    return ensure_object_tool_schema(
        to_openapi(parameters, custom_serializer=custom_serializer)
    )
