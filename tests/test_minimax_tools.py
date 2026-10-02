"""MiniMaxClient.generate_with_tools -- tool calling for the agent pipeline.

docs/STATUS.md known item 5: MiniMaxClient had no tool calling, so the
``src/llm/agents/`` pipeline was tool-less on MiniMax (the default provider).
These tests pin the contract the pipeline expects -- same signature and return
shape as ``DeepSeekClient.generate_with_tools`` -- against a mocked HTTP layer
(a fake aiohttp session); no real network is ever touched.
"""

from __future__ import annotations

import json
from typing import Any

import pytest

from src.llm.minimax_client import MiniMaxClient

# ---------------------------------------------------------------------------
# Fake HTTP layer (aiohttp-shaped)
# ---------------------------------------------------------------------------


class _FakeResponse:
    def __init__(self, status: int, payload: Any, content_type: str = "application/json"):
        self.status = status
        self.headers = {"Content-Type": content_type}
        self._payload = payload

    async def json(self):
        return self._payload

    async def text(self):
        return json.dumps(self._payload)

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _FakeSession:
    """Records every POST and replays canned responses in order."""

    def __init__(self, responses: list[_FakeResponse]):
        self._responses = list(responses)
        self.requests: list[tuple[str, dict]] = []

    def post(self, url: str, json: dict | None = None):
        self.requests.append((url, json))
        return self._responses.pop(0)


def _client_with(responses: list[_FakeResponse]) -> tuple[MiniMaxClient, _FakeSession]:
    from src.core.config import get_settings

    settings = get_settings()
    settings.llm.minimax.api_key = "sk-test-key-not-real"
    client = MiniMaxClient(settings)
    session = _FakeSession(responses)
    client.session = session
    return client, session


def _chat_response(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"id": "resp", "choices": [{"index": 0, "message": message, "finish_reason": "stop"}], "usage": {}}


def _tool_call(call_id: str, name: str, arguments: dict) -> dict:
    return {"id": call_id, "type": "function", "function": {"name": name, "arguments": json.dumps(arguments)}}


_TOOL = {
    "type": "function",
    "function": {
        "name": "get_price",
        "description": "Get the latest price for a symbol",
        "parameters": {
            "type": "object",
            "properties": {"symbol": {"type": "string"}},
            "required": ["symbol"],
        },
    },
}


# ---------------------------------------------------------------------------
# Tool-calling loop
# ---------------------------------------------------------------------------


async def test_tool_calls_response_is_parsed_and_final_answer_returned():
    """The core pipeline shape: model asks for tools, then answers."""
    calls: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        calls.append((name, args))
        return {"price": 599.25}

    client, session = _client_with(
        [
            _FakeResponse(200, _chat_response(tool_calls=[_tool_call("call_1", "get_price", {"symbol": "SPY"})])),
            _FakeResponse(200, _chat_response("<think>SPY is at 599.</think>SPY last traded at 599.25.")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "What is SPY trading at?"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    # Handler got the parsed call, not raw JSON string arguments.
    assert calls == [("get_price", {"symbol": "SPY"})]

    # Return shape is the raw final API response the pipeline consumes.
    assert response is not None
    assert response["choices"][0]["message"]["role"] == "assistant"
    # Think block stripped from the returned text.
    assert response["choices"][0]["message"]["content"] == "SPY last traded at 599.25."

    # Request bodies: first carries the tools; second carries tool results.
    first_url, first_payload = session.requests[0]
    assert first_url.endswith("/chat/completions")
    assert first_payload["tools"] == [_TOOL]
    assert first_payload["tool_choice"] == "auto"

    _, second_payload = session.requests[1]
    roles = [m["role"] for m in second_payload["messages"]]
    assert roles == ["user", "assistant", "tool"]
    assistant_msg = second_payload["messages"][1]
    assert assistant_msg["tool_calls"][0]["function"]["name"] == "get_price"
    tool_msg = second_payload["messages"][2]
    assert tool_msg["tool_call_id"] == "call_1"
    assert json.loads(tool_msg["content"]) == {"price": 599.25}


async def test_multiple_tool_calls_in_one_turn_are_all_executed():
    async def handler(name: str, args: dict) -> dict:
        return {"name": name, **args}

    client, _ = _client_with(
        [
            _FakeResponse(
                200,
                _chat_response(
                    tool_calls=[
                        _tool_call("call_a", "get_price", {"symbol": "SPY"}),
                        _tool_call("call_b", "get_price", {"symbol": "QQQ"}),
                    ]
                ),
            ),
            _FakeResponse(200, _chat_response("Both fetched.")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "SPY and QQQ prices"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert response["choices"][0]["message"]["content"] == "Both fetched."


async def test_plain_text_response_returns_without_calling_tools():
    """No tool_calls in the reply -> final response straight away."""
    calls: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        calls.append((name, args))
        return {}

    client, session = _client_with([_FakeResponse(200, _chat_response("Plain answer."))])

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert calls == []
    assert response["choices"][0]["message"]["content"] == "Plain answer."
    assert len(session.requests) == 1
    # Tools are still offered in the request body.
    assert session.requests[0][1]["tools"] == [_TOOL]


async def test_think_block_is_stripped_from_returned_text():
    """MiniMax-M3 inlines reasoning as <think>...</think>; the client must
    strip it (reusing agents.base.strip_think) from any returned text."""
    client, _ = _client_with([_FakeResponse(200, _chat_response("<think>chain of thought</think>The answer is 42."))])

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "Answer?"}],
        tools=[_TOOL],
        tool_handler=None,
    )

    assert response["choices"][0]["message"]["content"] == "The answer is 42."


async def test_tool_definition_shapes_are_normalised():
    """Bare and function-wrapped definitions both reach the API in OpenAI form."""

    async def handler(name: str, args: dict) -> dict:
        return {}

    bare = {"name": "get_price", "parameters": {"type": "object", "properties": {}}}
    client, session = _client_with([_FakeResponse(200, _chat_response("ok"))])

    await client.generate_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[bare],
        tool_handler=handler,
    )

    payload = session.requests[0][1]
    assert payload["tools"] == [{"type": "function", "function": bare}]


async def test_error_status_returns_none_like_other_clients():
    """A non-200 status must behave exactly like generate_completion: None."""
    client, _ = _client_with([_FakeResponse(500, {"error": "boom"})])

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[_TOOL],
        tool_handler=None,
    )

    assert response is None


async def test_max_turns_exhaustion_returns_last_response():
    """Model keeps calling tools -> loop stops at max_turns with the last response."""

    async def handler(name: str, args: dict) -> dict:
        return {"again": True}

    always_tools = _FakeResponse(200, _chat_response(tool_calls=[_tool_call("c", "get_price", {"symbol": "SPY"})]))
    client, _ = _client_with([always_tools, always_tools])

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "Loop forever"}],
        tools=[_TOOL],
        tool_handler=handler,
        max_turns=2,
    )

    # Last response (tool_calls message) is returned, not None, not a crash.
    assert response is not None
    assert "tool_calls" in response["choices"][0]["message"]


async def test_not_entered_raises_runtime_error():
    """Same guard as the other clients: use 'async with'."""
    from src.core.config import get_settings

    client = MiniMaxClient(get_settings())  # no session assigned

    with pytest.raises(RuntimeError, match="async with"):
        await client.generate_with_tools(
            messages=[{"role": "user", "content": "Hi"}],
            tools=[_TOOL],
            tool_handler=None,
        )


async def test_tool_handler_exception_becomes_error_result():
    """A crashing tool must not kill the loop; the model sees the error."""

    async def handler(name: str, args: dict) -> dict:
        raise ValueError("tool exploded")

    client, session = _client_with(
        [
            _FakeResponse(200, _chat_response(tool_calls=[_tool_call("call_1", "get_price", {"symbol": "SPY"})])),
            _FakeResponse(200, _chat_response("Recovered after tool error.")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert response["choices"][0]["message"]["content"] == "Recovered after tool error."
    tool_msg = session.requests[1][1]["messages"][2]
    assert json.loads(tool_msg["content"]) == {"error": "tool exploded"}


# ---------------------------------------------------------------------------
# generate_completion carries tools in the body
# ---------------------------------------------------------------------------


async def test_generate_completion_carries_tools_in_request_body():
    client, session = _client_with([_FakeResponse(200, _chat_response("ok"))])

    await client.generate_completion(
        messages=[{"role": "user", "content": "Hi"}],
        tools=[_TOOL],
    )

    payload = session.requests[0][1]
    assert payload["tools"] == [_TOOL]
    assert payload["tool_choice"] == "auto"


async def test_generate_completion_without_tools_keeps_old_payload():
    """Backward compatibility: no tools kwarg -> no tools/tool_choice keys."""
    client, session = _client_with([_FakeResponse(200, _chat_response("ok"))])

    await client.generate_completion(messages=[{"role": "user", "content": "Hi"}])

    payload = session.requests[0][1]
    assert "tools" not in payload
    assert "tool_choice" not in payload


# ---------------------------------------------------------------------------
# Hardening: argument types and id-less tool calls (cycle-4 review nits)
# ---------------------------------------------------------------------------


def _raw_call(name: str, arguments: Any, call_id: str | None = None) -> dict:
    """A tool_call with arguments exactly as the provider sent them."""
    tc: dict[str, Any] = {"type": "function", "function": {"name": name, "arguments": arguments}}
    if call_id is not None:
        tc["id"] = call_id
    return tc


def _tool_messages(session: _FakeSession) -> list[dict]:
    """The role:'tool' messages from the follow-up request body."""
    follow_up = session.requests[1][1]["messages"]
    return [m for m in follow_up if m["role"] == "tool"]


async def test_dict_typed_arguments_are_accepted_as_is():
    """Some providers return arguments already parsed; that must not crash."""
    calls: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        calls.append((name, args))
        return {"price": 599.25}

    client, session = _client_with(
        [
            _FakeResponse(200, _chat_response(tool_calls=[_raw_call("get_price", {"symbol": "SPY"}, "call_1")])),
            _FakeResponse(200, _chat_response("dict args worked")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "SPY?"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert calls == [("get_price", {"symbol": "SPY"})]
    # Valid dict args -> no error note in the fed-back result.
    (tool_msg,) = _tool_messages(session)
    assert json.loads(tool_msg["content"]) == {"price": 599.25}
    assert response["choices"][0]["message"]["content"] == "dict args worked"


async def test_invalid_json_arguments_degrade_to_empty_with_error_note():
    """Unparseable JSON string arguments: call the handler with {} and tell
    the model why its arguments were replaced."""
    calls: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        calls.append((name, args))
        return {"price": 1.0}

    client, session = _client_with(
        [
            _FakeResponse(200, _chat_response(tool_calls=[_raw_call("get_price", "{not json", "call_1")])),
            _FakeResponse(200, _chat_response("recovered")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "SPY?"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert calls == [("get_price", {})]
    (tool_msg,) = _tool_messages(session)
    content = json.loads(tool_msg["content"])
    assert "error" in content
    assert "arguments" in content["error"].lower()
    # The handler's own result is preserved alongside the note.
    assert content.get("price") == 1.0
    assert response["choices"][0]["message"]["content"] == "recovered"


async def test_null_arguments_degrade_to_empty_with_error_note():
    """arguments: null (or missing) is not valid json.loads input either."""
    calls: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        calls.append((name, args))
        return {"ok": True}

    client, session = _client_with(
        [
            _FakeResponse(200, _chat_response(tool_calls=[_raw_call("get_price", None, "call_1")])),
            _FakeResponse(200, _chat_response("null args recovered")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "SPY?"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert calls == [("get_price", {})]
    (tool_msg,) = _tool_messages(session)
    content = json.loads(tool_msg["content"])
    assert "error" in content
    assert response["choices"][0]["message"]["content"] == "null args recovered"


async def test_non_dict_json_arguments_degrade_to_empty_with_error_note():
    """A JSON string that parses to a non-object (list/number) is not tool args."""
    calls: list[tuple[str, dict]] = []

    async def handler(name: str, args: dict) -> dict:
        calls.append((name, args))
        return {"ok": True}

    client, _ = _client_with(
        [
            _FakeResponse(200, _chat_response(tool_calls=[_raw_call("get_price", "[1, 2, 3]", "call_1")])),
            _FakeResponse(200, _chat_response("list args recovered")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "SPY?"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    assert calls == [("get_price", {})]
    assert response["choices"][0]["message"]["content"] == "list args recovered"


async def test_two_id_less_calls_in_one_turn_get_distinct_tool_call_ids():
    """Fallback ids must not collide: unique per turn AND index."""

    async def handler(name: str, args: dict) -> dict:
        return {"price": 1.0}

    client, session = _client_with(
        [
            _FakeResponse(
                200,
                _chat_response(
                    tool_calls=[
                        _raw_call("get_price", '{"symbol": "SPY"}'),
                        _raw_call("get_price", '{"symbol": "QQQ"}'),
                    ]
                ),
            ),
            _FakeResponse(200, _chat_response("both done")),
        ]
    )

    response = await client.generate_with_tools(
        messages=[{"role": "user", "content": "SPY and QQQ"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    tool_msgs = _tool_messages(session)
    ids = [m["tool_call_id"] for m in tool_msgs]
    assert len(ids) == 2
    assert all(isinstance(i, str) and i for i in ids), f"ids must be non-empty strings, got {ids!r}"
    assert len(set(ids)) == 2, f"fallback ids collided: {ids!r}"
    assert response["choices"][0]["message"]["content"] == "both done"
