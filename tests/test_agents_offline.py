"""Offline tests for the agent layer (src/llm/agents).

These never call a provider: the ModelRouter is replaced by a fake, so they
pin how ``MarketAgent.execute()`` behaves when the routed client does or does
not support tool calling.
"""

from __future__ import annotations

from src.llm.agents.base import AgentResult, MarketAgent, strip_think


class _ProbeAgent(MarketAgent):
    AGENT_NAME = "probe"
    SYSTEM_PROMPT = "You are a probe."
    TOOL_NAMES = []
    CAPABILITY = "standard"


class _FakeRouter:
    def __init__(self, client):
        self._client = client

    async def route(self, capability):
        return self._client, "fake-model"

    async def __aenter__(self):
        return self

    async def __aexit__(self, *exc):
        return False


class _CompletionOnlyClient:
    """A client like MiniMaxClient: plain completions, no generate_with_tools."""

    def __init__(self, content="SPY looks fine to me."):
        self._content = content

    async def generate_completion(self, messages, model=None, max_tokens=300, temperature=0.3):
        return {"choices": [{"message": {"content": self._content}}]}


class _ToolCapableClient(_CompletionOnlyClient):
    """A client like DeepSeekClient."""

    def __init__(self, content="SPY is in an uptrend."):
        super().__init__(content)
        self.tools_requested = None
        self.handler_calls = []

    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        self.tools_requested = tools
        self.handler_calls.append(await tool_handler("get_ohlcv", {"symbol": "SPY"}))
        return {"choices": [{"message": {"content": self._content}}]}


def _agent_with(client) -> _ProbeAgent:
    agent = _ProbeAgent(registry=None, settings=None)
    agent._router = _FakeRouter(client)
    agent._entered = True
    return agent


# ---------------------------------------------------------------------------
# Tool-capable clients keep working
# ---------------------------------------------------------------------------


async def test_tool_capable_client_is_given_the_tools():
    client = _ToolCapableClient()
    agent = _agent_with(client)

    result = await agent.execute("Analyse SPY")

    assert isinstance(result, AgentResult)
    assert result.success
    assert client.tools_requested is not None
    assert client.handler_calls, "the tool handler was never called"
    assert result.tool_calls_made == ["get_ohlcv"]


# ---------------------------------------------------------------------------
# Clients without tool support must not look like success
# ---------------------------------------------------------------------------


async def test_client_without_tool_support_does_not_report_success():
    """A tool-less client cannot fetch data, so the agent must not claim it did.

    This is the default path today: the configured primary provider is MiniMax,
    whose client has no ``generate_with_tools``, so every agent used to return a
    confident-looking answer built from model memory with ``success=True``.
    """
    agent = _agent_with(_CompletionOnlyClient())

    result = await agent.execute("Fetch market data for SPY")

    assert not result.success, (
        "agent reported success without ever calling a tool -- the answer is "
        "model memory, not market data"
    )
    assert result.error, "a failed agent must say why"
    assert "generate_with_tools" in result.error
    assert _CompletionOnlyClient.__name__ in result.error, "the error must name the client"


async def test_client_without_tool_support_still_returns_the_model_text():
    """The text is kept for debugging, it just is not presented as a good result."""
    agent = _agent_with(_CompletionOnlyClient(content="SPY looks fine to me."))

    result = await agent.execute("Fetch market data for SPY")

    assert "SPY looks fine to me." in result.content


async def test_no_response_is_still_reported_as_a_failure():
    class _Silent(_CompletionOnlyClient):
        async def generate_completion(self, *args, **kwargs):
            return None

    agent = _agent_with(_Silent())

    result = await agent.execute("anything")

    assert not result.success
    assert result.error


# ---------------------------------------------------------------------------
# Result shape
# ---------------------------------------------------------------------------


def test_agent_result_defaults_to_success_with_no_tools():
    result = AgentResult(agent_name="x", content="hello")

    assert result.success is True
    assert result.tool_calls_made == []
    assert result.error is None


# ---------------------------------------------------------------------------
# Inline reasoning (MiniMax-M3 returns <think>...</think> inside content)
# ---------------------------------------------------------------------------


def test_strip_think_removes_an_inline_reasoning_block():
    content = "<think>The user wants SPY data. I should call get_ohlcv.</think>\n\nSPY is at 601.2."

    assert strip_think(content) == "SPY is at 601.2."


def test_strip_think_leaves_normal_content_untouched():
    assert strip_think("SPY is at 601.2.") == "SPY is at 601.2."


def test_strip_think_keeps_a_partial_tag():
    """An unterminated <think> must not silently delete the whole answer."""
    assert strip_think("<think>unterminated reasoning") == "<think>unterminated reasoning"


def test_strip_think_survives_empty_content():
    assert strip_think("") == ""
    assert strip_think(None) is None


async def test_agent_content_has_no_leaked_reasoning():
    """Reasoning models answer with <think>..</think> inline; that is not the answer."""
    raw = "<think>I should call get_ohlcv for SPY.</think>\n\nSPY closed at 601.20."
    agent = _agent_with(_ToolCapableClient(content=raw))

    result = await agent.execute("Analyse SPY")

    assert result.content.startswith("SPY closed at 601.20.")
    assert "<think>" not in result.content
    # The raw response is untouched -- only the surfaced text is cleaned.
    assert "<think>" in result.raw_response["choices"][0]["message"]["content"]
