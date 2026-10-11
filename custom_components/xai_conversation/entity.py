"""Base entity implementations for the xAI Conversation integration."""

from __future__ import annotations

import asyncio
import base64
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components import conversation
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm
from homeassistant.helpers.entity import Entity

from .client import (
    ResponseStreamParser,
    XAIClientError,
    assistant_items,
    build_responses_payload,
    function_tool,
    live_search_tools,
    system_message,
    tool_result_item,
    user_message,
)
from .const import (
    CONF_CHAT_MODEL,
    CONF_IMAGE_MODEL,
    CONF_LIVE_SEARCH,
    CONF_MAX_TOKENS,
    CONF_REASONING_EFFORT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DOMAIN,
    LOGGER,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_IMAGE_MODEL,
    RECOMMENDED_LIVE_SEARCH,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    XAI_IMAGE_MODELS,
    resolve_chat_reasoning_effort,
)
from .tool_schema import format_tool_parameters

MAX_TOOL_ITERATIONS = 6

if TYPE_CHECKING:
    from collections.abc import AsyncGenerator

    from homeassistant.config_entries import ConfigEntry, ConfigSubentry


class XAIBaseEntity(Entity):
    """Base entity for xAI conversation agents."""

    _attr_has_entity_name = True
    _attr_name = None

    def __init__(self, entry: ConfigEntry, subentry: ConfigSubentry) -> None:
        """Initialize the entity."""
        self.entry = entry
        self.subentry = subentry
        self._attr_unique_id = subentry.subentry_id
        self._attr_device_info = dr.DeviceInfo(
            identifiers={(DOMAIN, subentry.subentry_id)},
            name=subentry.title,
            manufacturer="xAI",
            model=subentry.data.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL),
            entry_type=dr.DeviceEntryType.SERVICE,
        )

    async def _async_handle_chat_log(
        self,
        chat_log: conversation.ChatLog,
        response_format: dict[str, Any] | None = None,
    ) -> None:
        """Generate a response for the provided chat log."""
        options = self.subentry.data
        tools = self._build_tools(chat_log, options)

        for iteration in range(MAX_TOOL_ITERATIONS):
            messages = await self._async_build_messages(list(chat_log.content))

            model = options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)
            reasoning_effort = self._resolve_reasoning_effort(model, options)

            payload = build_responses_payload(
                model=model,
                messages=messages,
                user=chat_log.conversation_id,
                max_tokens=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
                temperature=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
                top_p=options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
                reasoning_effort=reasoning_effort,
                tools=tools,
                response_format=response_format,
            )

            try:
                usage = await self._async_stream_chat_response(chat_log, payload)
            except XAIClientError as err:
                LOGGER.error("Error talking to xAI: %s", err)
                msg = f"Error talking to xAI: {err}"
                raise HomeAssistantError(msg) from err

            self._log_usage(chat_log, usage)

            if not chat_log.unresponded_tool_results:
                break

            LOGGER.debug(
                "Waiting for tool results before next xAI response (iteration %s)",
                iteration,
            )
        else:
            msg = "Too many tool interactions for xAI response"
            raise HomeAssistantError(msg)

    async def _async_build_messages(
        self, content: list[conversation.Content]
    ) -> list[dict[str, Any]]:
        """Convert chat log content to Responses API input items."""
        messages: list[dict[str, Any]] = []
        for item in content:
            if isinstance(item, conversation.SystemContent):
                messages.append(system_message(item.content))
                continue

            if isinstance(item, conversation.UserContent):
                messages.append(await self._async_user_message(item))
                continue

            if isinstance(item, conversation.AssistantContent):
                messages.extend(self._assistant_items(item))
                continue

            if isinstance(item, conversation.ToolResultContent):
                messages.append(tool_result_item(item.tool_call_id, item.tool_result))
                continue

        return messages

    async def _async_user_message(
        self, item: conversation.UserContent
    ) -> dict[str, Any]:
        """Build a user message with optional attachments."""
        images: list[tuple[str, str]] = []
        if item.attachments:
            images.extend(
                await asyncio.gather(
                    *(
                        self._async_attachment_image(attachment)
                        for attachment in item.attachments
                    )
                )
            )
        return user_message(item.content, images)

    def _assistant_items(
        self, item: conversation.AssistantContent
    ) -> list[dict[str, Any]]:
        """Build assistant text and function_call items."""
        tool_calls: list[dict[str, Any]] = []
        if item.tool_calls:
            tool_calls.extend(
                {
                    "id": tool_call.id,
                    "tool_name": tool_call.tool_name,
                    "tool_args": tool_call.tool_args,
                }
                for tool_call in item.tool_calls
            )
        return assistant_items(item.content, tool_calls)

    async def _async_attachment_image(
        self, attachment: conversation.Attachment
    ) -> tuple[str, str]:
        """Read an image attachment as ``(mime_type, base64)``."""
        path = Path(attachment.path)
        if not path.exists():
            msg = f"Attachment `{path}` does not exist"
            raise HomeAssistantError(msg)
        if not attachment.mime_type.startswith("image/"):
            msg = "xAI currently supports only image attachments"
            raise HomeAssistantError(msg)

        data = await self.hass.async_add_executor_job(path.read_bytes)
        return attachment.mime_type, base64.b64encode(data).decode()

    def _convert_tool_calls(self, calls: list[dict[str, Any]]) -> list[llm.ToolInput]:
        """Convert normalized tool calls into Home Assistant tool inputs."""
        results: list[llm.ToolInput] = []
        for call in calls:
            tool_name = call.get("tool_name")
            if not tool_name:
                continue
            arguments = call.get("tool_args") or {}
            if call_id := call.get("id"):
                results.append(
                    llm.ToolInput(
                        id=call_id,
                        tool_name=tool_name,
                        tool_args=arguments,
                    )
                )
            else:
                results.append(
                    llm.ToolInput(
                        tool_name=tool_name,
                        tool_args=arguments,
                    )
                )
        return results

    def _build_tools(
        self, chat_log: conversation.ChatLog, options: dict[str, Any]
    ) -> list[dict[str, Any]] | None:
        """Create tool definitions for the xAI request."""
        tools: list[dict[str, Any]] = []

        if chat_log.llm_api:
            serializer = (
                chat_log.llm_api.custom_serializer
                if chat_log.llm_api.custom_serializer
                else llm.selector_serializer
            )
            for tool in chat_log.llm_api.tools:
                try:
                    tools.append(
                        function_tool(
                            name=tool.name,
                            description=tool.description or "",
                            parameters=format_tool_parameters(
                                tool.parameters, custom_serializer=serializer
                            ),
                        )
                    )
                except Exception:  # noqa: BLE001 - skip tools xAI cannot accept
                    LOGGER.exception(
                        "Skipping Home Assistant tool %s for xAI", tool.name
                    )

        if options.get(CONF_LIVE_SEARCH, RECOMMENDED_LIVE_SEARCH):
            tools.extend(live_search_tools())

        return tools if tools else None

    def _resolve_reasoning_effort(
        self, model: str, options: dict[str, Any]
    ) -> str | None:
        """Choose a valid reasoning effort for the selected model."""
        reasoning_effort = options.get(CONF_REASONING_EFFORT)
        resolved = resolve_chat_reasoning_effort(model, reasoning_effort)
        if reasoning_effort and resolved != reasoning_effort:
            LOGGER.debug(
                "Adjusted reasoning effort %s to %s for model %s",
                reasoning_effort,
                resolved,
                model,
            )
        return resolved

    def _resolve_image_model(self, options: dict[str, Any]) -> str:
        """Choose a valid image model for image generation."""
        image_model = options.get(CONF_IMAGE_MODEL)
        if image_model:
            return image_model

        legacy_model = options.get(CONF_CHAT_MODEL)
        if legacy_model == "grok-2-image":
            return RECOMMENDED_IMAGE_MODEL

        if any(model_def["id"] == legacy_model for model_def in XAI_IMAGE_MODELS):
            return legacy_model

        return RECOMMENDED_IMAGE_MODEL

    def _notify_chat_log_server_tool_call(
        self, chat_log: Any, tool_call: dict[str, Any]
    ) -> None:
        """Notify listeners about a server-side tool call invocation."""
        if not (listener := chat_log.delta_listener):
            return

        listener(
            chat_log,
            {
                "role": "server_tool_call",
                "tool_call_id": tool_call.get("id"),
                "tool_name": tool_call.get("tool_name"),
                "tool_args": tool_call.get("tool_args") or {},
                "tool_type": tool_call.get("tool_type"),
            },
        )

    async def _async_stream_chat_response(
        self,
        chat_log: conversation.ChatLog,
        payload: dict[str, Any],
    ) -> dict[str, int | None] | None:
        """Stream the response from xAI and feed it into the chat log."""
        client = self.entry.runtime_data
        parser = ResponseStreamParser()

        async def _delta_stream() -> AsyncGenerator[dict[str, Any]]:
            async for event in client.stream_events(payload):
                for delta in parser.feed(event):
                    if server_tool := delta.get("server_tool_call"):
                        self._notify_chat_log_server_tool_call(chat_log, server_tool)
                        continue
                    if raw_calls := delta.get("tool_calls"):
                        converted = self._convert_tool_calls(raw_calls)
                        if not converted:
                            continue
                        yield {**delta, "tool_calls": converted}
                        continue
                    yield delta

            if parser.response is None and parser.usage is None:
                msg = "xAI stream returned no response"
                raise XAIClientError(msg)

        async for _ in chat_log.async_add_delta_content_stream(
            self.entity_id, _delta_stream()
        ):
            pass

        return parser.usage

    def _log_usage(
        self,
        chat_log: conversation.ChatLog,
        usage: dict[str, int | None] | None,
    ) -> None:
        """Record token usage statistics if available."""
        if usage is None:
            return
        chat_log.async_trace({"stats": usage})
