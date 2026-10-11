"""Tests for the xAI REST client, payload builders, and stream parser."""

from __future__ import annotations

import asyncio
import base64
import importlib.util
import json
import sys
from pathlib import Path

import httpx
import pytest

_CLIENT_PATH = (
    Path(__file__).resolve().parents[1]
    / "custom_components"
    / "xai_conversation"
    / "client.py"
)
_SPEC = importlib.util.spec_from_file_location("xai_rest_client", _CLIENT_PATH)
assert _SPEC is not None
assert _SPEC.loader is not None
_CLIENT = importlib.util.module_from_spec(_SPEC)
sys.modules["xai_rest_client"] = _CLIENT
_SPEC.loader.exec_module(_CLIENT)

XAI_API_BASE = _CLIENT.XAI_API_BASE
XAIClientError = _CLIENT.XAIClientError
XAIRestClient = _CLIENT.XAIRestClient
ResponseStreamParser = _CLIENT.ResponseStreamParser
assistant_items = _CLIENT.assistant_items
build_responses_payload = _CLIENT.build_responses_payload
decode_image_payload = _CLIENT.decode_image_payload
detect_image_mime = _CLIENT.detect_image_mime
extract_usage = _CLIENT.extract_usage
function_tool = _CLIENT.function_tool
iter_sse_events = _CLIENT.iter_sse_events
json_schema_format = _CLIENT.json_schema_format
live_search_tools = _CLIENT.live_search_tools
system_message = _CLIENT.system_message
tool_result_item = _CLIENT.tool_result_item
user_message = _CLIENT.user_message


def test_function_and_live_search_tools() -> None:
    """Client-side functions and server-side search tools use Responses API shapes."""
    tool = function_tool(
        "HassTurnOn",
        "Turn on a device",
        {"type": "object", "properties": {"name": {"type": "string"}}},
    )
    assert tool == {
        "type": "function",
        "name": "HassTurnOn",
        "description": "Turn on a device",
        "parameters": {"type": "object", "properties": {"name": {"type": "string"}}},
    }
    assert live_search_tools() == [{"type": "web_search"}, {"type": "x_search"}]


def test_json_schema_format() -> None:
    """Structured output uses the Responses API text.format object."""
    schema = {"type": "object", "properties": {"dogs": {"type": "integer"}}}
    assert json_schema_format(schema) == {
        "type": "json_schema",
        "name": "task_result",
        "schema": schema,
    }


def test_message_builders() -> None:
    """Conversation history maps onto Responses API input items."""
    assert system_message("Be helpful") == {"role": "system", "content": "Be helpful"}
    assert user_message("Hello") == {"role": "user", "content": "Hello"}

    image_msg = user_message("Look", [("image/png", "abc123")])
    assert image_msg["role"] == "user"
    assert image_msg["content"][0] == {"type": "input_text", "text": "Look"}
    assert image_msg["content"][1]["type"] == "input_image"
    assert image_msg["content"][1]["image_url"] == "data:image/png;base64,abc123"

    items = assistant_items(
        "Sure",
        [{"id": "call_1", "tool_name": "HassTurnOn", "tool_args": {"name": "lamp"}}],
    )
    assert items[0] == {"role": "assistant", "content": "Sure"}
    assert items[1] == {
        "type": "function_call",
        "name": "HassTurnOn",
        "arguments": '{"name": "lamp"}',
        "call_id": "call_1",
    }

    result = tool_result_item("call_1", {"ok": True})
    assert result == {
        "type": "function_call_output",
        "call_id": "call_1",
        "output": '{"ok": true}',
    }


def test_build_responses_payload_omits_optional_fields() -> None:
    """Reasoning, tools, and structured output are omitted when unused."""
    payload = build_responses_payload(
        model="grok-4.6",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=128,
        temperature=0.7,
        top_p=1.0,
        reasoning_effort=None,
        tools=None,
        user="conv-1",
    )
    assert payload["model"] == "grok-4.6"
    assert payload["store"] is False
    assert payload["parallel_tool_calls"] is True
    assert payload["user"] == "conv-1"
    assert "reasoning" not in payload
    assert "tools" not in payload
    assert "text" not in payload


def test_build_responses_payload_includes_reasoning_tools_and_schema() -> None:
    """Enabled options appear in the Responses request body."""
    tools = live_search_tools()
    schema = json_schema_format({"type": "object", "properties": {}})
    payload = build_responses_payload(
        model="grok-4.6",
        messages=[{"role": "user", "content": "hi"}],
        max_tokens=256,
        temperature=0.2,
        top_p=0.9,
        reasoning_effort="low",
        tools=tools,
        user=None,
        response_format=schema,
    )
    assert payload["reasoning"] == {"effort": "low"}
    assert payload["tools"] == tools
    assert payload["text"] == {"format": schema}
    assert "user" not in payload


def test_extract_usage_accepts_both_usage_shapes() -> None:
    """Responses and Chat Completions usage keys both map to HA stats."""
    assert extract_usage({"input_tokens": 10, "output_tokens": 4}) == {
        "input_tokens": 10,
        "output_tokens": 4,
    }
    assert extract_usage({"prompt_tokens": 8, "completion_tokens": 2}) == {
        "input_tokens": 8,
        "output_tokens": 2,
    }
    assert extract_usage(None) is None


def test_decode_image_payload_and_mime() -> None:
    """Image helpers strip data-URI prefixes and detect PNG/JPEG."""
    png = b"\x89PNG\r\n\x1a\n" + b"rest"
    jpeg = b"\xff\xd8" + b"rest"
    assert decode_image_payload(png) == png
    encoded = base64.b64encode(jpeg).decode()
    assert decode_image_payload(f"data:image/jpeg;base64,{encoded}") == jpeg
    assert detect_image_mime(png) == "image/png"
    assert detect_image_mime(jpeg) == "image/jpeg"
    with pytest.raises(XAIClientError, match="No image data"):
        decode_image_payload(None)


def test_iter_sse_events_parses_named_and_data_only_events() -> None:
    """SSE parser accepts event/data pairs, data-only JSON, comments, and [DONE]."""

    async def _lines() -> object:
        completed = {
            "type": "response.completed",
            "response": {"usage": {"input_tokens": 1, "output_tokens": 2}},
        }
        for line in (
            ": keep-alive",
            "event: response.output_text.delta",
            'data: {"delta": "Hi"}',
            "",
            f"data: {json.dumps(completed)}",
            "",
            "data: [DONE]",
            "",
        ):
            yield line

    async def _collect() -> list[dict[str, object]]:
        return [event async for event in iter_sse_events(_lines())]

    events = asyncio.run(_collect())
    assert [event.get("type") for event in events] == [
        "response.output_text.delta",
        "response.completed",
    ]
    assert events[0]["delta"] == "Hi"


def test_stream_parser_text_thinking_tools_and_usage() -> None:
    """Parser emits HA chat-log deltas for text, reasoning, and function calls."""
    parser = ResponseStreamParser()

    deltas = parser.feed(
        {"type": "response.output_item.added", "item": {"type": "message"}}
    )
    assert deltas == [{"role": "assistant"}]

    assert parser.feed({"type": "response.output_text.delta", "delta": "Hello"}) == [
        {"content": "Hello"}
    ]
    assert parser.feed(
        {"type": "response.reasoning_summary_text.delta", "delta": "think"}
    ) == [{"thinking_content": "think"}]

    tool_deltas = parser.feed(
        {
            "type": "response.output_item.done",
            "item": {
                "type": "function_call",
                "call_id": "call_1",
                "name": "HassTurnOn",
                "arguments": '{"name": "lamp"}',
            },
        }
    )
    assert tool_deltas == [
        {
            "tool_calls": [
                {
                    "id": "call_1",
                    "tool_name": "HassTurnOn",
                    "tool_args": {"name": "lamp"},
                }
            ]
        }
    ]
    # Duplicate done / arguments.done events must not emit twice.
    assert (
        parser.feed(
            {
                "type": "response.function_call_arguments.done",
                "call_id": "call_1",
                "name": "HassTurnOn",
                "arguments": '{"name": "lamp"}',
            }
        )
        == []
    )

    server = parser.feed(
        {
            "type": "response.output_item.done",
            "item": {
                "type": "web_search_call",
                "id": "ws_1",
                "action": {"query": "weather"},
            },
        }
    )
    assert server[0]["server_tool_call"]["tool_name"] == "web_search"
    assert server[0]["server_tool_call"]["tool_type"] == "web_search_call"

    parser.feed(
        {
            "type": "response.completed",
            "response": {"usage": {"input_tokens": 11, "output_tokens": 5}},
        }
    )
    assert parser.usage == {"input_tokens": 11, "output_tokens": 5}


def test_stream_parser_chat_completions_fallback() -> None:
    """Chat Completions chunks are accepted as a compatibility fallback."""
    parser = ResponseStreamParser()
    deltas = parser.feed(
        {
            "object": "chat.completion.chunk",
            "choices": [
                {
                    "delta": {
                        "role": "assistant",
                        "content": "Hi",
                        "reasoning_content": "hmm",
                        "tool_calls": [
                            {
                                "id": "call_2",
                                "function": {
                                    "name": "HassTurnOff",
                                    "arguments": "{}",
                                },
                            }
                        ],
                    }
                }
            ],
            "usage": {"prompt_tokens": 3, "completion_tokens": 1},
        }
    )
    assert {"role": "assistant"} in deltas
    assert {"content": "Hi"} in deltas
    assert {"thinking_content": "hmm"} in deltas
    assert deltas[-1]["tool_calls"][0]["tool_name"] == "HassTurnOff"
    assert parser.usage == {"input_tokens": 3, "output_tokens": 1}


def test_stream_parser_failed_and_incomplete() -> None:
    """Failed / incomplete events become XAIClientError."""
    parser = ResponseStreamParser()
    with pytest.raises(XAIClientError, match="boom"):
        parser.feed(
            {
                "type": "response.failed",
                "response": {"error": {"message": "boom"}},
            }
        )

    parser = ResponseStreamParser()
    with pytest.raises(XAIClientError, match="max output tokens reached"):
        parser.feed(
            {
                "type": "response.incomplete",
                "response": {"incomplete_details": {"reason": "max_output_tokens"}},
            }
        )


def _http_client(handler: httpx.MockTransport) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=handler)


def test_list_models_success() -> None:
    """list_models reads OpenAI-compatible /v1/models payloads."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url) == f"{XAI_API_BASE}/models"
        assert request.headers["Authorization"] == "Bearer test-key"
        return httpx.Response(
            200,
            json={"object": "list", "data": [{"id": "grok-4.6"}]},
        )

    http = _http_client(httpx.MockTransport(handler))
    client = XAIRestClient("test-key", http, timeout=5, generate_timeout=5)

    async def _run() -> list[dict[str, object]]:
        try:
            return await client.list_models()
        finally:
            await http.aclose()

    assert asyncio.run(_run()) == [{"id": "grok-4.6"}]


def test_list_models_error_uses_api_message() -> None:
    """HTTP errors surface the API error message."""

    def handler(_request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": "Invalid API key"}})

    http = _http_client(httpx.MockTransport(handler))
    client = XAIRestClient("test-key", http, timeout=5, generate_timeout=5)

    async def _run() -> None:
        try:
            await client.list_models()
        finally:
            await http.aclose()

    with pytest.raises(XAIClientError, match="Invalid API key") as err:
        asyncio.run(_run())
    assert err.value.status_code == httpx.codes.UNAUTHORIZED


def test_generate_image_decodes_b64() -> None:
    """Image generation requests b64_json and returns decoded bytes."""
    jpeg = b"\xff\xd8JFIF"

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/images/generations")
        body = json.loads(request.content)
        assert body["response_format"] == "b64_json"
        assert body["model"] == "grok-imagine-image-2.0"
        return httpx.Response(
            200,
            json={"data": [{"b64_json": base64.b64encode(jpeg).decode()}]},
        )

    http = _http_client(httpx.MockTransport(handler))
    client = XAIRestClient("test-key", http, timeout=5, generate_timeout=5)

    async def _run() -> tuple[bytes, str]:
        try:
            return await client.generate_image(
                prompt="a lamp", model="grok-imagine-image-2.0"
            )
        finally:
            await http.aclose()

    image_bytes, mime = asyncio.run(_run())
    assert image_bytes == jpeg
    assert mime == "image/jpeg"


def test_stream_events_posts_responses_and_parses_sse() -> None:
    """stream_events POSTs /v1/responses with stream=true and yields events."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert str(request.url).endswith("/responses")
        body = json.loads(request.content)
        assert body["stream"] is True
        assert body["store"] is False
        completed = {
            "type": "response.completed",
            "response": {"usage": {"input_tokens": 2, "output_tokens": 1}},
        }
        sse = (
            'data: {"type": "response.output_text.delta", "delta": "Yo"}\n\n'
            f"data: {json.dumps(completed)}\n\n"
            "data: [DONE]\n\n"
        )
        return httpx.Response(200, text=sse)

    http = _http_client(httpx.MockTransport(handler))
    client = XAIRestClient("test-key", http, timeout=5, generate_timeout=5)

    async def _run() -> list[dict[str, object]]:
        try:
            return [
                event
                async for event in client.stream_events(
                    {"model": "grok-4.6", "input": [{"role": "user", "content": "hi"}]}
                )
            ]
        finally:
            await http.aclose()

    events = asyncio.run(_run())
    assert events[0]["delta"] == "Yo"
    assert events[1]["type"] == "response.completed"


def test_manifest_has_no_xai_sdk_requirement() -> None:
    """The integration must install without xai-sdk / protobuf."""
    manifest = json.loads(
        (
            Path(__file__).resolve().parents[1]
            / "custom_components"
            / "xai_conversation"
            / "manifest.json"
        ).read_text()
    )
    assert "xai-sdk" not in " ".join(manifest.get("requirements") or [])
    assert manifest["version"] == "1.4.0"
