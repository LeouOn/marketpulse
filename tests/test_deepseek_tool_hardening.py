"""DeepSeekClient.generate_with_tools -- tool-argument hardening.

Same contract as MiniMaxClient (see tests/test_minimax_tools.py): provider
tool-call ``arguments`` arrive in more shapes than "JSON string"; every
unusable shape must degrade to ``{}`` with an error note fed back to the
model, and fallback ``tool_call_id``s must stay unique per turn AND index.
The HTTP layer is a fake aiohttp session -- no real network is ever touched.
"""

from __future__ import annotations

import json
from typing import Any

from src.llm.deepseek_client import DeepSeekClient

# ---------------------------------------------------------------------------
# Fake HTTP layer (aiohttp-shaped, same as tests/test_minimax_tools.py)
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


def _client_with(responses: list[_FakeResponse]) -> tuple[DeepSeekClient, _FakeSession]:
    from src.core.config import get_settings

    settings = get_settings()
    settings.llm.deepseek.api_key = "sk-test-key-not-real"
    client = DeepSeekClient(settings)
    session = _FakeSession(responses)
    client.session = session
    return client, session


def _chat_response(content: str | None = None, tool_calls: list[dict] | None = None) -> dict:
    message: dict[str, Any] = {"role": "assistant", "content": content}
    if tool_calls:
        message["tool_calls"] = tool_calls
    return {"id": "resp", "choices": [{"index": 0, "message": message, "finish_reason": "stop"}], "usage": {}}


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


_TOOL = {
    "type": "function",
    "function": {
        "name": "get_price",
        "description": "Get the latest price for a symbol.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
    },
}


# ---------------------------------------------------------------------------
# The hardening contract
# ---------------------------------------------------------------------------


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
        messages=[{"role": "user", "content": "SPY and QQQ?"}],
        tools=[_TOOL],
        tool_handler=handler,
    )

    tool_ids = [m["tool_call_id"] for m in _tool_messages(session)]
    assert len(tool_ids) == 2
    assert len(set(tool_ids)) == 2, f"fallback tool_call_ids collided: {tool_ids}"
    assert response["choices"][0]["message"]["content"] == "both done"
