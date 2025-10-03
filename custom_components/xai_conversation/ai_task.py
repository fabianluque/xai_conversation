"""AI Task integration for the xAI integration."""

from __future__ import annotations

import json
from typing import TYPE_CHECKING

from homeassistant.components import ai_task, conversation
from homeassistant.exceptions import HomeAssistantError

from .const import LOGGER
from .entity import XAIBaseEntity

if TYPE_CHECKING:
    from homeassistant.config_entries import ConfigEntry, ConfigSubentry
    from homeassistant.core import HomeAssistant
    from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

    from . import XAIConfigEntry


async def async_setup_entry(
    _hass: HomeAssistant,
    config_entry: ConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up AI Task entities."""
    entities_by_subentry: dict[str | None, list[XAITaskEntity]] = {}

    for subentry in config_entry.subentries.values():
        if subentry.subentry_type != "ai_task":
            continue

        entity = XAITaskEntity(config_entry, subentry)
        entities_by_subentry.setdefault(subentry.subentry_id, []).append(entity)

    for subentry_id, entities in entities_by_subentry.items():
        if subentry_id is not None:
            async_add_entities(entities, config_subentry_id=subentry_id)
        else:
            async_add_entities(entities)


class XAITaskEntity(
    ai_task.AITaskEntity,
    XAIBaseEntity,
):
    """xAI AI Task entity."""

    def __init__(self, entry: XAIConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the entity."""
        super().__init__(entry, subentry)
        self._attr_supported_features = (
            ai_task.AITaskEntityFeature.GENERATE_DATA
            | ai_task.AITaskEntityFeature.SUPPORT_ATTACHMENTS
        )
        # xAI supports image generation through certain models
        # For now, we'll assume image generation is supported
        self._attr_supported_features |= ai_task.AITaskEntityFeature.GENERATE_IMAGE

    async def _async_generate_data(
        self,
        task: ai_task.GenDataTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenDataTaskResult:
        """Handle a generate data task."""
        await self._async_handle_chat_log(chat_log)

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            msg = "Last content in chat log is not an AssistantContent"
            raise HomeAssistantError(msg)

        text = chat_log.content[-1].content or ""

        if not task.structure:
            return ai_task.GenDataTaskResult(
                conversation_id=chat_log.conversation_id,
                data=text,
            )
        try:
            data = json.loads(text)
        except json.JSONDecodeError as err:
            LOGGER.error(
                "Failed to parse JSON response: %s. Response: %s",
                err,
                text,
            )
            msg = f"Failed to parse JSON response: {err}"
            raise HomeAssistantError(msg) from err

        return ai_task.GenDataTaskResult(
            conversation_id=chat_log.conversation_id,
            data=data,
        )

    async def _async_generate_image(
        self,
        _task: ai_task.GenImageTask,
        chat_log: conversation.ChatLog,
    ) -> ai_task.GenImageTaskResult:
        """Handle a generate image task."""
        # For now, we'll use the same chat log handling as data generation
        # In a real implementation, this would need to be adapted for image generation
        await self._async_handle_chat_log(chat_log)

        if not isinstance(chat_log.content[-1], conversation.AssistantContent):
            msg = "Last content in chat log is not an AssistantContent"
            raise HomeAssistantError(msg)

        # This is a placeholder - xAI might not support image generation directly
        # We would need to check if the response contains image data
        msg = "Image generation is not currently supported by xAI"
        raise HomeAssistantError(msg)
