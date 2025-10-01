"""Constants for the xAI Conversation integration."""

from __future__ import annotations

import logging
from typing import Final

from homeassistant.const import CONF_LLM_HASS_API
from homeassistant.helpers import llm

DOMAIN: Final = "xai_conversation"
DEFAULT_NAME: Final = "xAI Conversation"
DEFAULT_CONVERSATION_NAME: Final = DEFAULT_NAME

CONF_CHAT_MODEL: Final = "chat_model"
CONF_MAX_TOKENS: Final = "max_tokens"
CONF_TEMPERATURE: Final = "temperature"
CONF_TOP_P: Final = "top_p"
CONF_PROMPT: Final = "prompt"
CONF_RECOMMENDED: Final = "recommended"
CONF_REASONING_EFFORT: Final = "reasoning_effort"
CONF_LIVE_SEARCH: Final = "live_search"

RECOMMENDED_CHAT_MODEL: Final = "grok-4-fast-non-reasoning"
RECOMMENDED_MAX_TOKENS: Final = 4096
RECOMMENDED_TEMPERATURE: Final = 0.7
RECOMMENDED_TOP_P: Final = 1.0
RECOMMENDED_REASONING_EFFORT: Final = "medium"
RECOMMENDED_LIVE_SEARCH: Final = True
PROGRESS_MESSAGE: Final = "Let me take care of that for you..."

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
