"""Tests for xAI model catalog and reasoning-effort helpers."""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

_MODELS_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "xai_conversation"
    / "models.py"
)
_SPEC = importlib.util.spec_from_file_location("xai_models", _MODELS_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_MODELS = importlib.util.module_from_spec(_SPEC)
sys.modules["xai_models"] = _MODELS
_SPEC.loader.exec_module(_MODELS)

RECOMMENDED_CHAT_MODEL = _MODELS.RECOMMENDED_CHAT_MODEL
RECOMMENDED_IMAGE_MODEL = _MODELS.RECOMMENDED_IMAGE_MODEL
RECOMMENDED_REASONING_EFFORT = _MODELS.RECOMMENDED_REASONING_EFFORT
XAI_CHAT_MODELS = _MODELS.XAI_CHAT_MODELS
XAI_IMAGE_MODELS = _MODELS.XAI_IMAGE_MODELS
resolve_chat_reasoning_effort = _MODELS.resolve_chat_reasoning_effort


def test_recommended_defaults_point_at_current_mainline_models() -> None:
    """Recommended chat/image models should match current xAI mainline IDs."""
    assert RECOMMENDED_CHAT_MODEL == "grok-4.6"
    assert RECOMMENDED_IMAGE_MODEL == "grok-imagine-image-2.0"
    assert RECOMMENDED_REASONING_EFFORT == "low"


def test_chat_picker_includes_4_6_4_5_and_4_3() -> None:
    """Chat picker should expose the mainline Grok 4.x text models."""
    assert [model["id"] for model in XAI_CHAT_MODELS] == [
        "grok-4.6",
        "grok-4.5",
        "grok-4.3",
    ]


def test_image_picker_includes_imagine_2_0_and_legacy() -> None:
    """Image picker should prefer Imagine 2.0 while keeping the prior model."""
    assert [model["id"] for model in XAI_IMAGE_MODELS] == [
        "grok-imagine-image-2.0",
        "grok-imagine-image",
    ]


def test_resolve_reasoning_effort_for_grok_4_6() -> None:
    """Grok 4.6 supports low/medium/high/xhigh and maps none → low."""
    assert resolve_chat_reasoning_effort("grok-4.6", "low") == "low"
    assert resolve_chat_reasoning_effort("grok-4.6", "xhigh") == "xhigh"
    assert resolve_chat_reasoning_effort("grok-4.6", "none") == "low"
    assert resolve_chat_reasoning_effort("grok-4.6", None) is None


def test_resolve_reasoning_effort_for_grok_4_5() -> None:
    """Grok 4.5 maps unsupported none/xhigh onto available efforts."""
    assert resolve_chat_reasoning_effort("grok-4.5", "medium") == "medium"
    assert resolve_chat_reasoning_effort("grok-4.5", "none") == "low"
    assert resolve_chat_reasoning_effort("grok-4.5", "xhigh") == "high"


def test_resolve_reasoning_effort_for_grok_4_3() -> None:
    """Grok 4.3 keeps none and xhigh as first-class options."""
    assert resolve_chat_reasoning_effort("grok-4.3", "none") == "none"
    assert resolve_chat_reasoning_effort("grok-4.3", "xhigh") == "xhigh"
    assert resolve_chat_reasoning_effort("grok-4.3", "high") == "high"
