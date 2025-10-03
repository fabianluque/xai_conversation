"""AI Task integration for the xAI integration."""

from __future__ import annotations

import base64
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
        # Extract the user's prompt directly from the task or last user message
        # Don't process through chat log as image generation needs a direct prompt
        prompt = None

        # Look for the last user message in the chat log
        for content in reversed(chat_log.content):
            if isinstance(content, conversation.UserContent):
                prompt = content.content
                break

        if not prompt:
            msg = "No prompt provided for image generation"
            raise HomeAssistantError(msg)

        client = self.entry.runtime_data

        try:
            response = await client.image.sample(
                prompt=prompt,
                model="grok-2-image",
                image_format="base64",
            )
        except Exception as err:
            LOGGER.error("Failed to generate image: %s", err)
            msg = f"Failed to generate image: {err}"
            raise HomeAssistantError(msg) from err

        # Get the image data from response
        # Try base64 attribute first, then fallback to image property
        image_data = getattr(response, "base64", None) or response.image

        # Check if it's a coroutine and await if needed
        if hasattr(image_data, "__await__"):
            image_data = await image_data

        if not image_data:
            msg = "No image data received from xAI"
            raise HomeAssistantError(msg)

        # If image_data is a string, it's base64-encoded and needs to be decoded
        if isinstance(image_data, str):
            try:
                # Strip data URI prefix if present (e.g., "data:image/jpeg;base64,")
                if image_data.startswith("data:"):
                    # Find the comma that separates the header from the data
                    comma_index = image_data.find(",")
                    if comma_index != -1:
                        image_data = image_data[comma_index + 1 :]

                image_data = base64.b64decode(image_data)
            except Exception as err:
                LOGGER.error("Failed to decode base64 image data: %s", err)
                msg = f"Failed to decode image data: {err}"
                raise HomeAssistantError(msg) from err

        # Detect the image format from the magic bytes
        mime_type = "image/jpeg"  # Default to JPEG as xAI returns JPEG
        if image_data[:8] == b"\x89PNG\r\n\x1a\n":
            mime_type = "image/png"
        elif image_data[:2] == b"\xff\xd8":
            mime_type = "image/jpeg"

        return ai_task.GenImageTaskResult(
            conversation_id=chat_log.conversation_id,
            image_data=image_data,
            mime_type=mime_type,
        )
