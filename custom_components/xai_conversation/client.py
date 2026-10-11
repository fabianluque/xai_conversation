"""
HTTP client for the xAI REST / Responses API.

Home Assistant 2026.10 pins protobuf 7, while every released ``xai-sdk``
still requires ``protobuf<7``. Talking to ``https://api.x.ai/v1`` over
httpx (already shipped by Home Assistant) avoids that conflict and keeps
chat, tools, live search, streaming, structured output, and images.
"""

from __future__ import annotations

import base64
import json
from dataclasses import dataclass, field
from typing import Any, Final

import httpx

XAI_API_BASE: Final = "https://api.x.ai/v1"
DEFAULT_TIMEOUT: Final = 30.0
GENERATE_READ_TIMEOUT: Final = 300.0
IMAGE_READ_TIMEOUT: Final = 120.0
CONNECT_TIMEOUT: Final = 10.0

_DONE: Final = object()
_SERVER_TOOL_TYPES: Final = frozenset(
    {
        "web_search_call",
        "x_search_call",
        "code_interpreter_call",
        "code_execution_call",
        "file_search_call",
        "image_generation_call",
    }
)


class XAIClientError(Exception):
    """Raised when the xAI HTTP API cannot be reached or returns an error."""

    def __init__(self, message: str, *, status_code: int | None = None) -> None:
        """Initialize the error."""
        super().__init__(message)
        self.status_code = status_code


def function_tool(
    name: str, description: str, parameters: dict[str, Any]
) -> dict[str, Any]:
    """Build a client-side function tool for the Responses API."""
    return {
        "type": "function",
        "name": name,
        "description": description,
        "parameters": parameters,
    }


def live_search_tools() -> list[dict[str, Any]]:
    """Return xAI server-side web and X search tools."""
    return [{"type": "web_search"}, {"type": "x_search"}]


def json_schema_format(
    schema: dict[str, Any], *, name: str = "task_result"
) -> dict[str, Any]:
    """Build a Responses API structured-output format from a JSON schema."""
    return {
        "type": "json_schema",
        "name": name,
        "schema": schema,
    }


def system_message(content: str) -> dict[str, Any]:
    """Build a system/developer input message."""
    return {"role": "system", "content": content}


def user_message(
    text: str | None,
    images: list[tuple[str, str]] | None = None,
) -> dict[str, Any]:
    """
    Build a user message, optionally with base64 image attachments.

    ``images`` is a list of ``(mime_type, base64_payload)`` pairs.
    """
    parts: list[dict[str, Any]] = []
    if text:
        parts.append({"type": "input_text", "text": text})
    for mime_type, encoded in images or []:
        parts.append(
            {
                "type": "input_image",
                "image_url": f"data:{mime_type};base64,{encoded}",
                "detail": "auto",
            }
        )
    if len(parts) == 1 and parts[0]["type"] == "input_text":
        return {"role": "user", "content": text or ""}
    return {"role": "user", "content": parts or [{"type": "input_text", "text": ""}]}


def assistant_items(
    content: str | None,
    tool_calls: list[dict[str, Any]] | None = None,
) -> list[dict[str, Any]]:
    """Build assistant text plus function_call items for conversation replay."""
    items: list[dict[str, Any]] = []
    if content:
        items.append({"role": "assistant", "content": content})
    for call in tool_calls or []:
        item: dict[str, Any] = {
            "type": "function_call",
            "name": call["tool_name"],
            "arguments": json.dumps(call.get("tool_args") or {}),
        }
        if call_id := call.get("id"):
            item["call_id"] = call_id
        items.append(item)
    if not items:
        items.append({"role": "assistant", "content": ""})
    return items


def tool_result_item(call_id: str | None, result: Any) -> dict[str, Any]:
    """Build a function_call_output item from a Home Assistant tool result."""
    output = result if isinstance(result, str) else json.dumps(result)
    item: dict[str, Any] = {
        "type": "function_call_output",
        "output": output,
    }
    if call_id:
        item["call_id"] = call_id
    return item


def build_responses_payload(  # noqa: PLR0913
    *,
    model: str,
    messages: list[dict[str, Any]],
    max_tokens: int,
    temperature: float,
    top_p: float,
    reasoning_effort: str | None,
    tools: list[dict[str, Any]] | None,
    user: str | None,
    response_format: dict[str, Any] | None = None,
) -> dict[str, Any]:
    """Assemble a ``POST /v1/responses`` body (``stream`` is added by the client)."""
    payload: dict[str, Any] = {
        "model": model,
        "input": messages,
        "max_output_tokens": max_tokens,
        "temperature": temperature,
        "top_p": top_p,
        "store": False,
        "parallel_tool_calls": True,
    }
    if user:
        payload["user"] = user
    if reasoning_effort:
        payload["reasoning"] = {"effort": reasoning_effort}
    if tools:
        payload["tools"] = tools
    if response_format:
        payload["text"] = {"format": response_format}
    return payload


def extract_usage(usage: dict[str, Any] | None) -> dict[str, int | None] | None:
    """Normalize Responses / Chat Completions usage into HA chat-log stats."""
    if not usage:
        return None
    return {
        "input_tokens": usage.get("input_tokens", usage.get("prompt_tokens")),
        "output_tokens": usage.get("output_tokens", usage.get("completion_tokens")),
    }


def decode_image_payload(image_data: str | bytes | None) -> bytes:
    """Decode a base64 image payload, including optional data-URI prefixes."""
    if image_data is None:
        msg = "No image data received from xAI"
        raise XAIClientError(msg)
    if isinstance(image_data, bytes):
        return image_data
    payload = image_data
    if payload.startswith("data:"):
        comma_index = payload.find(",")
        if comma_index != -1:
            payload = payload[comma_index + 1 :]
    try:
        return base64.b64decode(payload)
    except ValueError as err:
        msg = f"Failed to decode image data: {err}"
        raise XAIClientError(msg) from err


def detect_image_mime(image_data: bytes, fallback: str = "image/jpeg") -> str:
    """Detect PNG/JPEG from magic bytes."""
    if image_data[:8] == b"\x89PNG\r\n\x1a\n":
        return "image/png"
    if image_data[:2] == b"\xff\xd8":
        return "image/jpeg"
    return fallback


def _decode_sse_data(
    data_lines: list[str], event_name: str | None
) -> dict[str, Any] | object | None:
    """Parse accumulated SSE data lines into an event dict, ``[DONE]``, or None."""
    raw = "\n".join(data_lines).strip()
    if not raw:
        return None
    if raw == "[DONE]":
        return _DONE
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return None
    if not isinstance(parsed, dict):
        return None
    if event_name and "type" not in parsed:
        parsed["type"] = event_name
    return parsed


async def iter_sse_events(lines: Any) -> Any:
    """Yield JSON objects from an SSE line iterator."""
    event_name: str | None = None
    data_lines: list[str] = []

    async for raw_line in lines:
        line = raw_line.rstrip("\r")
        if line == "":
            if data_lines:
                event = _decode_sse_data(data_lines, event_name)
                if event is _DONE:
                    return
                if isinstance(event, dict):
                    yield event
            event_name = None
            data_lines = []
            continue
        if line.startswith(":"):
            continue
        if line.startswith("event:"):
            event_name = line[6:].strip()
            continue
        if line.startswith("data:"):
            data_lines.append(line[5:].lstrip())

    if data_lines:
        event = _decode_sse_data(data_lines, event_name)
        if event is not _DONE and isinstance(event, dict):
            yield event


def _parse_tool_arguments(raw: Any) -> dict[str, Any]:
    """Parse a tool-call arguments payload into a dict."""
    if raw in (None, ""):
        return {}
    if isinstance(raw, dict):
        return raw
    try:
        parsed = json.loads(raw)
    except json.JSONDecodeError:
        return {"raw_arguments": raw}
    if isinstance(parsed, dict):
        return parsed
    return {"raw_arguments": raw}


def _function_call_delta(item: dict[str, Any]) -> dict[str, Any] | None:
    """Turn a function_call item / event into a normalized tool-call dict."""
    name = item.get("name") or (item.get("function") or {}).get("name")
    if not name:
        return None
    call_id = item.get("call_id") or item.get("id")
    arguments = item.get("arguments")
    if arguments is None:
        arguments = (item.get("function") or {}).get("arguments")
    result: dict[str, Any] = {
        "tool_name": name,
        "tool_args": _parse_tool_arguments(arguments),
    }
    if call_id:
        result["id"] = call_id
    return result


def _server_tool_delta(item: dict[str, Any]) -> dict[str, Any]:
    """Normalize a server-side tool call for UI notifications."""
    item_type = item.get("type") or "server_tool_call"
    tool_name = item.get("name") or item_type.removesuffix("_call")
    action = item.get("action") or item.get("arguments") or {}
    return {
        "id": item.get("id") or item.get("call_id"),
        "tool_name": tool_name,
        "tool_args": _parse_tool_arguments(action),
        "tool_type": item_type,
    }


@dataclass
class ResponseStreamParser:
    """Convert Responses API (or Chat Completions) stream events into deltas."""

    usage: dict[str, int | None] | None = None
    response: dict[str, Any] | None = None
    _assistant_started: bool = False
    _emitted_call_ids: set[str] = field(default_factory=set)
    _seen_server_ids: set[str] = field(default_factory=set)

    def _ensure_assistant(self) -> list[dict[str, Any]]:
        if self._assistant_started:
            return []
        self._assistant_started = True
        return [{"role": "assistant"}]

    def _text_delta(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        return [*self._ensure_assistant(), {"content": text}]

    def _thinking_delta(self, text: str) -> list[dict[str, Any]]:
        if not text:
            return []
        return [*self._ensure_assistant(), {"thinking_content": text}]

    def _emit_function_call(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        call = _function_call_delta(item)
        if call is None:
            return []
        call_key = str(call.get("id") or f"{call['tool_name']}:{call['tool_args']}")
        if call_key in self._emitted_call_ids:
            return []
        self._emitted_call_ids.add(call_key)
        return [*self._ensure_assistant(), {"tool_calls": [call]}]

    def _emit_server_tool(self, item: dict[str, Any]) -> list[dict[str, Any]]:
        marker = str(item.get("id") or item.get("call_id") or item.get("type") or "")
        if marker and marker in self._seen_server_ids:
            return []
        if marker:
            self._seen_server_ids.add(marker)
        return [{"server_tool_call": _server_tool_delta(item)}]

    def _capture_usage(self, response: dict[str, Any]) -> None:
        self.response = response
        if usage := extract_usage(response.get("usage")):
            self.usage = usage

    def _chat_chunk(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        deltas: list[dict[str, Any]] = []
        if usage := extract_usage(event.get("usage")):
            self.usage = usage
        choices = event.get("choices") or []
        if not choices:
            return deltas
        delta = choices[0].get("delta") or {}
        if content := delta.get("content"):
            deltas.extend(self._text_delta(content))
        if reasoning := delta.get("reasoning_content"):
            deltas.extend(self._thinking_delta(reasoning))
        for tool_call in delta.get("tool_calls") or []:
            merged = {
                "id": tool_call.get("id"),
                "call_id": tool_call.get("id"),
                "name": (tool_call.get("function") or {}).get("name"),
                "arguments": (tool_call.get("function") or {}).get("arguments"),
            }
            deltas.extend(self._emit_function_call(merged))
        return deltas

    def feed(self, event: dict[str, Any]) -> list[dict[str, Any]]:
        """Consume one stream event and return chat-log deltas."""
        event_type = event.get("type")
        handlers = {
            "response.output_text.delta": lambda: self._text_delta(
                event.get("delta") or ""
            ),
            "response.reasoning_text.delta": lambda: self._thinking_delta(
                event.get("delta") or ""
            ),
            "response.reasoning_summary_text.delta": lambda: self._thinking_delta(
                event.get("delta") or ""
            ),
            "response.output_item.added": lambda: self._item_event(
                event.get("item") or {}, done=False
            ),
            "response.output_item.done": lambda: self._item_event(
                event.get("item") or {}, done=True
            ),
            "response.function_call_arguments.done": lambda: self._emit_function_call(
                event
            ),
            "response.completed": lambda: self._terminal_event(event_type, event),
            "response.failed": lambda: self._terminal_event(event_type, event),
            "response.incomplete": lambda: self._terminal_event(event_type, event),
            "response.error": lambda: self._terminal_event(event_type, event),
        }
        if handler := handlers.get(event_type):
            return handler()
        if event.get("object") == "chat.completion.chunk":
            return self._chat_chunk(event)
        return []

    def _terminal_event(
        self, event_type: str, event: dict[str, Any]
    ) -> list[dict[str, Any]]:
        """Handle completed / failed / incomplete / error stream events."""
        if event_type == "response.completed":
            self._capture_usage(event.get("response") or {})
            return []
        if event_type == "response.failed":
            response = event.get("response") or {}
            self._capture_usage(response)
            error = response.get("error") or {}
            message = error.get("message") or "xAI response failed"
            raise XAIClientError(message)
        if event_type == "response.incomplete":
            response = event.get("response") or {}
            self._capture_usage(response)
            details = response.get("incomplete_details") or {}
            reason = details.get("reason") or "unknown reason"
            if reason == "max_output_tokens":
                reason = "max output tokens reached"
            msg = f"xAI response incomplete: {reason}"
            raise XAIClientError(msg)
        message = event.get("message") or "xAI response error"
        raise XAIClientError(message)

    def _item_event(self, item: dict[str, Any], *, done: bool) -> list[dict[str, Any]]:
        item_type = item.get("type")
        if item_type == "function_call" and done:
            return self._emit_function_call(item)
        if item_type in _SERVER_TOOL_TYPES:
            return self._emit_server_tool(item)
        if item_type in {"message", "reasoning"} and not self._assistant_started:
            return self._ensure_assistant()
        return []


class XAIRestClient:
    """Minimal async client for the xAI REST API."""

    def __init__(
        self,
        api_key: str,
        http_client: httpx.AsyncClient,
        *,
        timeout: float = DEFAULT_TIMEOUT,
        generate_timeout: float = GENERATE_READ_TIMEOUT,
    ) -> None:
        """
        Initialize the client.

        ``http_client`` should be Home Assistant's shared httpx client.
        """
        self._api_key = api_key
        self._client = http_client
        self._timeout = timeout
        self._generate_timeout = generate_timeout

    def _headers(self) -> dict[str, str]:
        return {
            "Authorization": f"Bearer {self._api_key}",
            "Content-Type": "application/json",
        }

    def _request_timeout(self, read: float) -> httpx.Timeout:
        return httpx.Timeout(
            connect=CONNECT_TIMEOUT,
            read=read,
            write=30.0,
            pool=10.0,
        )

    def _error_message(self, response: httpx.Response) -> str:
        try:
            payload = response.json()
        except ValueError:
            text = response.text.strip()
            return text or f"xAI API error {response.status_code}"
        if isinstance(payload, dict):
            error = payload.get("error")
            if isinstance(error, dict) and error.get("message"):
                return str(error["message"])
            if isinstance(error, str):
                return error
            if payload.get("message"):
                return str(payload["message"])
        return f"xAI API error {response.status_code}"

    def _raise_for_status(self, response: httpx.Response) -> None:
        if not response.is_error:
            return
        raise XAIClientError(
            self._error_message(response),
            status_code=response.status_code,
        )

    async def list_models(self) -> list[dict[str, Any]]:
        """Validate the API key by listing available models."""
        try:
            response = await self._client.get(
                f"{XAI_API_BASE}/models",
                headers=self._headers(),
                timeout=self._request_timeout(self._timeout),
            )
        except httpx.HTTPError as err:
            msg = f"Unable to connect to xAI: {err}"
            raise XAIClientError(msg) from err
        self._raise_for_status(response)
        payload = response.json()
        if isinstance(payload, dict):
            data = payload.get("data", [])
            if isinstance(data, list):
                return data
        msg = "Unexpected xAI models response"
        raise XAIClientError(msg)

    async def generate_image(self, *, prompt: str, model: str) -> tuple[bytes, str]:
        """Generate one image and return ``(bytes, mime_type)``."""
        try:
            response = await self._client.post(
                f"{XAI_API_BASE}/images/generations",
                headers=self._headers(),
                json={
                    "model": model,
                    "prompt": prompt,
                    "n": 1,
                    "response_format": "b64_json",
                },
                timeout=self._request_timeout(IMAGE_READ_TIMEOUT),
            )
        except httpx.HTTPError as err:
            msg = f"Failed to generate image: {err}"
            raise XAIClientError(msg) from err
        self._raise_for_status(response)
        payload = response.json()
        items = payload.get("data") if isinstance(payload, dict) else None
        if not items:
            msg = "No image data received from xAI"
            raise XAIClientError(msg)
        item = items[0]
        raw = item.get("b64_json") or item.get("url")
        image_bytes = decode_image_payload(raw)
        mime_type = item.get("mime_type") or detect_image_mime(image_bytes)
        return image_bytes, mime_type

    async def stream_events(self, payload: dict[str, Any]) -> Any:
        """POST a streaming Responses request and yield parsed SSE events."""
        body = {**payload, "stream": True, "store": False}
        try:
            async with self._client.stream(
                "POST",
                f"{XAI_API_BASE}/responses",
                headers=self._headers(),
                json=body,
                timeout=self._request_timeout(self._generate_timeout),
            ) as response:
                if response.is_error:
                    await response.aread()
                    self._raise_for_status(response)
                async for event in iter_sse_events(response.aiter_lines()):
                    yield event
        except XAIClientError:
            raise
        except httpx.HTTPError as err:
            msg = f"Error talking to xAI: {err}"
            raise XAIClientError(msg) from err
