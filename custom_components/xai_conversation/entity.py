"""Base entity implementations for the xAI Conversation integration."""

from __future__ import annotations

import asyncio
import base64
import json
from pathlib import Path
from typing import TYPE_CHECKING, Any

from homeassistant.components import conversation
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers import llm
from homeassistant.helpers.entity import Entity
from voluptuous_openapi import convert
from xai_sdk.chat import (
    SearchParameters,
)
from xai_sdk.chat import (
    image as chat_image,
)
from xai_sdk.chat import (
    system as chat_system,
)
from xai_sdk.chat import (
    text as chat_text,
)
from xai_sdk.chat import (
    tool as chat_tool,
)
from xai_sdk.chat import (
    tool_result as chat_tool_result,
)
from xai_sdk.chat import (
    user as chat_user,
)
from xai_sdk.proto import chat_pb2

from .const import (
    CONF_CHAT_MODEL,
    CONF_LIVE_SEARCH,
    CONF_MAX_SEARCH_RESULTS,
    CONF_MAX_TOKENS,
    CONF_REASONING_EFFORT,
    CONF_TEMPERATURE,
    CONF_TOP_P,
    DOMAIN,
    LOGGER,
    PROGRESS_MESSAGE,
    RECOMMENDED_CHAT_MODEL,
    RECOMMENDED_LIVE_SEARCH,
    RECOMMENDED_MAX_SEARCH_RESULTS,
    RECOMMENDED_MAX_TOKENS,
    RECOMMENDED_TEMPERATURE,
    RECOMMENDED_TOP_P,
    XAI_MODELS,
)

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

    async def _async_handle_chat_log(self, chat_log: conversation.ChatLog) -> None:
        """Generate a response for the provided chat log."""
        options = self.subentry.data
        client = self.entry.runtime_data

        tools = self._build_tools(chat_log)
        search_parameters = self._build_search_parameters(options)

        progress_message_sent = False

        for iteration in range(MAX_TOOL_ITERATIONS):
            messages = await self._async_build_messages(list(chat_log.content))

            model = options.get(CONF_CHAT_MODEL, RECOMMENDED_CHAT_MODEL)
            reasoning_effort = self._resolve_reasoning_effort(model, options)

            chat_request = client.chat.create(
                model=model,
                conversation_id=chat_log.conversation_id,
                messages=messages,
                user=chat_log.conversation_id,
                max_tokens=options.get(CONF_MAX_TOKENS, RECOMMENDED_MAX_TOKENS),
                temperature=options.get(CONF_TEMPERATURE, RECOMMENDED_TEMPERATURE),
                top_p=options.get(CONF_TOP_P, RECOMMENDED_TOP_P),
                reasoning_effort=reasoning_effort,
                search_parameters=search_parameters,
                tools=tools,
                parallel_tool_calls=True,
                store_messages=False,
            )

            (
                final_response,
                streamed_output,
                streamed_tool_call,
            ) = await self._async_stream_chat_response(chat_log, chat_request)

            self._log_usage(chat_log, final_response)

            if streamed_tool_call and not streamed_output and not progress_message_sent:
                self._notify_chat_log_progress(chat_log)
                progress_message_sent = True

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
    ) -> list[chat_pb2.Message]:
        """Convert chat log content to xAI message objects."""
        messages: list[chat_pb2.Message] = []
        for item in content:
            if isinstance(item, conversation.SystemContent):
                messages.append(chat_system(item.content))
                continue

            if isinstance(item, conversation.UserContent):
                messages.append(await self._async_user_message(item))
                continue

            if isinstance(item, conversation.AssistantContent):
                messages.append(self._assistant_message(item))
                continue

            if isinstance(item, conversation.ToolResultContent):
                messages.append(chat_tool_result(json.dumps(item.tool_result)))
                continue

        return messages

    async def _async_user_message(
        self, item: conversation.UserContent
    ) -> chat_pb2.Message:
        """Build a user message with optional attachments."""
        parts: list[chat_pb2.Content] = []
        if item.content:
            parts.append(chat_text(item.content))
        if item.attachments:
            parts.extend(
                await asyncio.gather(
                    *(
                        self._async_attachment_content(attachment)
                        for attachment in item.attachments
                    )
                )
            )
        return chat_user(*parts) if parts else chat_user(chat_text(""))

    def _assistant_message(
        self, item: conversation.AssistantContent
    ) -> chat_pb2.Message:
        """Build an assistant message including tool calls."""
        message = chat_pb2.Message(role=chat_pb2.MessageRole.ROLE_ASSISTANT)
        if item.content:
            message.content.extend([chat_text(item.content)])
        if item.tool_calls:
            for tool_call in item.tool_calls:
                arguments = json.dumps(tool_call.tool_args)
                message.tool_calls.append(
                    chat_pb2.ToolCall(
                        id=tool_call.id,
                        function=chat_pb2.FunctionCall(
                            name=tool_call.tool_name,
                            arguments=arguments,
                        ),
                    )
                )
        return message

    async def _async_attachment_content(
        self, attachment: conversation.Attachment
    ) -> chat_pb2.Content:
        """Convert an attachment to xAI content."""
        path = Path(attachment.path)
        if not path.exists():
            msg = f"Attachment `{path}` does not exist"
            raise HomeAssistantError(msg)
        if not attachment.mime_type.startswith("image/"):
            msg = "xAI currently supports only image attachments"
            raise HomeAssistantError(msg)

        data = await self.hass.async_add_executor_job(path.read_bytes)
        encoded = base64.b64encode(data).decode()
        return chat_image(f"data:{attachment.mime_type};base64,{encoded}")

    def _convert_tool_calls(
        self, calls: list[chat_pb2.ToolCall]
    ) -> list[llm.ToolInput]:
        """Convert xAI tool calls into Home Assistant tool inputs."""
        results: list[llm.ToolInput] = []
        for call in calls:
            if not call.function.name:
                continue
            try:
                arguments = (
                    json.loads(call.function.arguments)
                    if call.function.arguments
                    else {}
                )
            except json.JSONDecodeError:
                arguments = {"raw_arguments": call.function.arguments}
            if call.id:
                results.append(
                    llm.ToolInput(
                        id=call.id,
                        tool_name=call.function.name,
                        tool_args=arguments,
                    )
                )
            else:
                results.append(
                    llm.ToolInput(
                        tool_name=call.function.name,
                        tool_args=arguments,
                    )
                )
        return results

    def _build_tools(
        self, chat_log: conversation.ChatLog
    ) -> list[chat_pb2.Tool] | None:
        """Create tool definitions for the xAI request."""
        if not chat_log.llm_api:
            return None

        serializer = (
            chat_log.llm_api.custom_serializer
            if chat_log.llm_api.custom_serializer
            else llm.selector_serializer
        )

        return [
            chat_tool(
                name=tool.name,
                description=tool.description,
                parameters=convert(tool.parameters, custom_serializer=serializer),
            )
            for tool in chat_log.llm_api.tools
        ]

    def _build_search_parameters(
        self, options: dict[str, Any]
    ) -> SearchParameters | None:
        """Derive live search settings for the request."""
        if options.get(CONF_LIVE_SEARCH, RECOMMENDED_LIVE_SEARCH):
            max_results = options.get(
                CONF_MAX_SEARCH_RESULTS, RECOMMENDED_MAX_SEARCH_RESULTS
            )
            return SearchParameters(mode="on", max_search_results=max_results)
        if options.get(CONF_LIVE_SEARCH) is not None:
            return SearchParameters(mode="off")
        return None

    def _resolve_reasoning_effort(
        self, model: str, options: dict[str, Any]
    ) -> str | None:
        """Choose a valid reasoning effort for the selected model."""
        reasoning_effort = options.get(CONF_REASONING_EFFORT)
        if not reasoning_effort:
            return None

        # Check if the selected model supports reasoning
        model_supports_reasoning = any(
            model_def["id"] == model and model_def["supports_reasoning"]
            for model_def in XAI_MODELS
        )

        if not model_supports_reasoning:
            LOGGER.debug(
                "Skipping reasoning effort %s for non-reasoning model %s",
                reasoning_effort,
                model,
            )
            return None

        return reasoning_effort

    def _notify_chat_log_progress(self, chat_log: Any) -> None:
        """Send a friendly progress update to the listener."""
        if not (listener := chat_log.delta_listener):
            return

        listener(
            chat_log,
            {
                "role": "assistant",
                "content": PROGRESS_MESSAGE,
            },
        )

    def _notify_chat_log_assistant_delta(
        self,
        chat_log: Any,
        content: Any,
    ) -> None:
        """Notify listeners about assistant output."""
        if not (listener := chat_log.delta_listener):
            return

        delta: dict[str, Any] = {"role": "assistant"}
        if content.content is not None:
            delta["content"] = content.content
        if content.thinking_content is not None:
            delta["thinking_content"] = content.thinking_content
        if content.tool_calls is not None:
            delta["tool_calls"] = content.tool_calls

        listener(chat_log, delta)

    def _notify_chat_log_tool_result(
        self,
        chat_log: Any,
        tool_result: Any,
    ) -> None:
        """Notify listeners about tool results."""
        if not (listener := chat_log.delta_listener):
            return

        listener(
            chat_log,
            {
                "role": "tool_result",
                "agent_id": tool_result.agent_id,
                "tool_call_id": tool_result.tool_call_id,
                "tool_name": tool_result.tool_name,
                "tool_result": tool_result.tool_result,
            },
        )

    async def _async_stream_chat_response(
        self,
        chat_log: conversation.ChatLog,
        chat_request: Any,
    ) -> tuple[Any, bool, bool]:
        """Stream the response from xAI and feed it into the chat log."""
        final_response: Any | None = None
        streamed_output = False
        streamed_tool_call = False

        async def _delta_stream(
            request: Any = chat_request,
        ) -> AsyncGenerator[dict[str, Any]]:
            nonlocal final_response, streamed_output, streamed_tool_call
            assistant_started = False

            async for response, chunk in request.stream():
                final_response = response

                for choice in chunk.choices:
                    emitted_delta = False

                    if choice.content:
                        if not assistant_started:
                            yield {"role": "assistant"}
                            assistant_started = True
                        yield {"content": choice.content}
                        streamed_output = True
                        emitted_delta = True

                    if choice.reasoning_content:
                        if not assistant_started:
                            yield {"role": "assistant"}
                            assistant_started = True
                        yield {"thinking_content": choice.reasoning_content}
                        streamed_output = True
                        emitted_delta = True

                    if choice.tool_calls:
                        tool_inputs = self._convert_tool_calls(list(choice.tool_calls))
                        if tool_inputs:
                            if not assistant_started:
                                yield {"role": "assistant"}
                                assistant_started = True
                            yield {"tool_calls": tool_inputs}
                            streamed_tool_call = True
                            emitted_delta = True

                    if (
                        not assistant_started
                        and choice.role == chat_pb2.MessageRole.ROLE_ASSISTANT
                        and not emitted_delta
                    ):
                        yield {"role": "assistant"}
                        assistant_started = True

            if final_response is not None:
                yield {"native": final_response}

        async for _ in chat_log.async_add_delta_content_stream(
            self.entity_id, _delta_stream()
        ):
            pass

        if final_response is None:
            msg = "xAI stream returned no response"
            raise HomeAssistantError(msg)

        return final_response, streamed_output, streamed_tool_call

    def _log_usage(self, chat_log: conversation.ChatLog, response: Any) -> None:
        """Record token usage statistics if available."""
        usage = getattr(response, "usage", None)
        if usage is None:
            return
        chat_log.async_trace(
            {
                "stats": {
                    "input_tokens": getattr(usage, "prompt_tokens", None),
                    "output_tokens": getattr(usage, "completion_tokens", None),
                }
            }
        )
