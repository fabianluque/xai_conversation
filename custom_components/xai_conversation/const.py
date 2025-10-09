"""Constants for the xAI Conversation integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm
from homeassistant.helpers.selector import SelectOptionDict

DOMAIN: Final = "xai_conversation"
DEFAULT_NAME: Final = "xAI Conversation"
DEFAULT_CONVERSATION_NAME: Final = DEFAULT_NAME
DEFAULT_AI_TASK_NAME: Final = "xAI AI Task"

CONF_CHAT_MODEL: Final = "chat_model"
CONF_MAX_TOKENS: Final = "max_tokens"
CONF_TEMPERATURE: Final = "temperature"
CONF_TOP_P: Final = "top_p"
CONF_PROMPT: Final = "prompt"
CONF_RECOMMENDED: Final = "recommended"
CONF_REASONING_EFFORT: Final = "reasoning_effort"
CONF_LIVE_SEARCH: Final = "live_search"
CONF_MAX_SEARCH_RESULTS: Final = "max_search_results"

RECOMMENDED_CHAT_MODEL: Final = "grok-4-fast-non-reasoning"
RECOMMENDED_MAX_TOKENS: Final = 4096
RECOMMENDED_TEMPERATURE: Final = 0.7
RECOMMENDED_TOP_P: Final = 1.0
RECOMMENDED_REASONING_EFFORT: Final = "medium"
RECOMMENDED_LIVE_SEARCH: Final = False
RECOMMENDED_MAX_SEARCH_RESULTS: Final = 5

# xAI model definitions with reasoning support
XAI_MODELS: Final = [
    {
        "id": "grok-4-fast-reasoning",
        "name": "Grok 4 Fast (Reasoning)",
        "supports_reasoning": True,
    },
    {
        "id": "grok-4-fast-non-reasoning",
        "name": "Grok 4 Fast (Non-reasoning)",
        "supports_reasoning": False,
    },
    {
        "id": "grok-4",
        "name": "Grok 4",
        "supports_reasoning": True,
    },
    {
        "id": "grok-3-mini",
        "name": "Grok 3 Mini",
        "supports_reasoning": True,
    },
    {
        "id": "grok-3",
        "name": "Grok 3",
        "supports_reasoning": True,
    },
    {
        "id": "grok-2-image",
        "name": "Grok 2 Image",
        "supports_reasoning": False,
    },
]

# Reasoning effort options
REASONING_OPTIONS: Final = [
    SelectOptionDict(value="low", label="Low"),
    SelectOptionDict(value="medium", label="Medium"),
    SelectOptionDict(value="high", label="High"),
]

LOGGER = logging.getLogger(__package__)

RECOMMENDED_CONVERSATION_OPTIONS: Final = {
    CONF_RECOMMENDED: True,
    CONF_CHAT_MODEL: RECOMMENDED_CHAT_MODEL,
    CONF_MAX_TOKENS: RECOMMENDED_MAX_TOKENS,
    CONF_TEMPERATURE: RECOMMENDED_TEMPERATURE,
    CONF_TOP_P: RECOMMENDED_TOP_P,
    CONF_LIVE_SEARCH: RECOMMENDED_LIVE_SEARCH,
    CONF_PROMPT: llm.DEFAULT_INSTRUCTIONS_PROMPT,
    CONF_LLM_HASS_API: [llm.LLM_API_ASSIST],
}

RECOMMENDED_AI_TASK_OPTIONS: Final = {
    CONF_RECOMMENDED: True,
    CONF_CHAT_MODEL: RECOMMENDED_CHAT_MODEL,
    CONF_MAX_TOKENS: RECOMMENDED_MAX_TOKENS,
    CONF_TEMPERATURE: RECOMMENDED_TEMPERATURE,
    CONF_TOP_P: RECOMMENDED_TOP_P,
    CONF_LIVE_SEARCH: RECOMMENDED_LIVE_SEARCH,
}
