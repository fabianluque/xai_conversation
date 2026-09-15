"""xAI model catalog and reasoning-effort helpers."""

from __future__ import annotations

from typing import Any, Final

# Recommended defaults for new conversation / AI Task entries.
RECOMMENDED_CHAT_MODEL: Final = "grok-4.6"
RECOMMENDED_IMAGE_MODEL: Final = "grok-imagine-image-2.0"
# Grok 4.6 cannot disable reasoning; low is the fastest supported effort.
RECOMMENDED_REASONING_EFFORT: Final = "low"

# Chat models from https://docs.x.ai/docs/models (mainline aliases only).
XAI_CHAT_MODELS: Final[list[dict[str, Any]]] = [
    {
        "id": "grok-4.6",
        "name": "Grok 4.6",
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        # Reasoning cannot be disabled on 4.6.
        "reasoning_efforts": ["low", "medium", "high", "xhigh"],
    },
    {
        "id": "grok-4.5",
        "name": "Grok 4.5",
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        # Reasoning cannot be disabled; xhigh is coerced to high by the API.
        "reasoning_efforts": ["low", "medium", "high"],
    },
    {
        "id": "grok-4.3",
        "name": "Grok 4.3",
        "supports_reasoning": True,
        "supports_reasoning_effort": True,
        "reasoning_efforts": ["none", "low", "medium", "high", "xhigh"],
    },
]

XAI_IMAGE_MODELS: Final[list[dict[str, Any]]] = [
    {
        "id": "grok-imagine-image-2.0",
        "name": "Grok Imagine Image 2.0",
    },
    {
        "id": "grok-imagine-image",
        "name": "Grok Imagine Image",
    },
]


def get_chat_model(model_id: str) -> dict[str, Any] | None:
    """Return the catalog entry for a chat model id, if known."""
    return next(
        (model_def for model_def in XAI_CHAT_MODELS if model_def["id"] == model_id),
        None,
    )


def resolve_chat_reasoning_effort(
    model: str, reasoning_effort: str | None
) -> str | None:
    """
    Return a reasoning_effort value accepted by the selected chat model.

    Unsupported values are mapped when a close alternative exists (for example
    ``none`` → ``low`` on models that cannot disable reasoning, or ``xhigh`` →
    ``high`` when xhigh is unavailable). Otherwise ``None`` is returned so the
    SDK omits the parameter.
    """
    if not reasoning_effort:
        return None

    model_def = get_chat_model(model)
    if model_def is None or not model_def.get("supports_reasoning_effort", False):
        return None

    supported = model_def.get("reasoning_efforts")
    if not supported:
        return reasoning_effort

    if reasoning_effort in supported:
        return reasoning_effort

    fallbacks = {
        "none": "low",
        "xhigh": "high",
    }
    mapped = fallbacks.get(reasoning_effort)
    if mapped is not None and mapped in supported:
        return mapped

    return None
