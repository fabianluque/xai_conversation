"""Tests for xAI tool schema conversion helpers."""

from __future__ import annotations

import importlib.util
import json
import sys
from pathlib import Path

import pytest
from probatio import (
    UNSUPPORTED,
    Optional,
    Required,
    Schema,
)
from probatio import (
    Any as ProbatioAny,
)

_TOOL_SCHEMA_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "xai_conversation"
    / "tool_schema.py"
)
_SPEC = importlib.util.spec_from_file_location("tool_schema", _TOOL_SCHEMA_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_TOOL_SCHEMA = importlib.util.module_from_spec(_SPEC)
sys.modules["tool_schema"] = _TOOL_SCHEMA
_SPEC.loader.exec_module(_TOOL_SCHEMA)

ensure_object_tool_schema = _TOOL_SCHEMA.ensure_object_tool_schema
format_tool_parameters = _TOOL_SCHEMA.format_tool_parameters
sanitize_schema = _TOOL_SCHEMA.sanitize_schema


def test_sanitize_schema_replaces_unsupported() -> None:
    """UNSUPPORTED markers must become JSON-serializable."""
    schema = {
        "type": "object",
        "properties": {
            "ok": {"type": "string"},
            "bad": UNSUPPORTED,
        },
    }

    sanitized = sanitize_schema(schema)

    assert sanitized == {
        "type": "object",
        "properties": {
            "ok": {"type": "string"},
            "bad": {},
        },
    }
    json.dumps(sanitized)  # must not raise


def test_ensure_object_unwraps_union_root() -> None:
    """Prefer an object branch when the schema root is a union."""
    schema = {
        "anyOf": [
            {
                "type": "object",
                "properties": {
                    "hours": {"type": "integer"},
                    "minutes": {"type": "integer"},
                },
            },
            {"type": "null"},
        ],
        "description": "Start a timer",
    }

    result = ensure_object_tool_schema(schema)

    assert result["type"] == "object"
    assert "anyOf" not in result
    assert result["properties"]["hours"]["type"] == "integer"
    assert result["description"] == "Start a timer"
    json.dumps(result)


def test_ensure_object_strips_required_any_composition() -> None:
    """HassStartTimer-style Required(Any(...)) keeps object shape without anyOf."""
    schema = {
        "type": "object",
        "properties": {
            "hours": {"type": "integer"},
            "minutes": {"type": "integer"},
            "seconds": {"type": "integer"},
            "name": {"type": "string"},
        },
        "additionalProperties": False,
        "anyOf": [
            {"required": ["hours"]},
            {"required": ["minutes"]},
            {"required": ["seconds"]},
        ],
    }

    result = ensure_object_tool_schema(schema)

    assert result["type"] == "object"
    assert "anyOf" not in result
    assert set(result["properties"]) == {"hours", "minutes", "seconds", "name"}
    json.dumps(result)


def test_format_tool_parameters_for_hass_start_timer() -> None:
    """End-to-end convert of Assist timer slot schema."""
    parameters = Schema(
        {
            Required(ProbatioAny("hours", "minutes", "seconds")): int,
            Optional("name"): str,
            Optional("conversation_command"): str,
        }
    )

    result = format_tool_parameters(parameters)

    assert result["type"] == "object"
    assert "anyOf" not in result
    assert "oneOf" not in result
    assert "hours" in result["properties"]
    json.dumps(result)


@pytest.mark.parametrize(
    "value",
    [
        None,
        "string",
        ["not", "an", "object"],
        42,
    ],
)
def test_ensure_object_wraps_non_dicts(value: object) -> None:
    """Non-object schemas are wrapped so xAI still accepts the tool."""
    result = ensure_object_tool_schema(value)
    assert result["type"] == "object"
    assert "properties" in result
    json.dumps(result)
