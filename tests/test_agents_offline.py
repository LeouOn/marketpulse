"""Offline tests for the agent layer (src/llm/agents).

No provider, no network, no local config: the ModelRouter, the tool registry and
the settings are all fakes, so these pin how ``MarketAgent.execute()`` behaves
when the routed client does or does not support tool calling.
"""

from __future__ import annotations

from src.llm.agents.base import AgentResult, MarketAgent, strip_think

# ---------------------------------------------------------------------------
# Fakes
# ---------------------------------------------------------------------------

OHLCV_TOOL = {
    "type": "function",
    "function": {
        "name": "get_ohlcv",
        "description": "Fetch OHLCV bars.",
        "parameters": {"type": "object", "properties": {"symbol": {"type": "string"}}},
    },
}


class _FakeRegistry:
    """Stands in for ToolRegistry; records dispatches instead of calling Yahoo."""

    def __init__(self, definitions=(OHLCV_TOOL,)):
        self._definitions = list(definitions)
        self.dispatched: list[tuple[str, dict]] = []

    def list_definitions(self, names):
        # The real registry filters by name; a fake that returned everything would
        # make a tool-less agent look like it had tools.
        wanted = set(names or ())
        return [d for d in self._definitions if d["function"]["name"] in wanted]

    def get_tool_names(self):
        return [d["function"]["name"] for d in self._definitions]

    async def dispatch(self, name, args):
        self.dispatched.append((name, args))
        return {"symbol": args.get("symbol"), "rows": 3}


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

    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        self.tools_requested = tools
        await tool_handler("get_ohlcv", {"symbol": "SPY"})
        return {"choices": [{"message": {"content": self._content}}]}


class _DataProbeAgent(MarketAgent):
    """An agent that expects to fetch data, like DataAgent."""

    AGENT_NAME = "data_probe"
    SYSTEM_PROMPT = "You are a data probe."
    TOOL_NAMES = ["get_ohlcv"]
    CAPABILITY = "standard"


class _ReasoningProbeAgent(MarketAgent):
    """An agent that never wanted data, like CritiqueAgent (TOOL_NAMES = [])."""

    AGENT_NAME = "reasoning_probe"
    SYSTEM_PROMPT = "You are a reasoning probe."
    TOOL_NAMES = []
    CAPABILITY = "reasoning"


def _agent_with(agent_cls, client) -> MarketAgent:
    agent = agent_cls(registry=_FakeRegistry(), settings=object())
    agent._router = _FakeRouter(client)
    agent._entered = True
    return agent


# ---------------------------------------------------------------------------
# Tool-capable clients get the agent's tools
# ---------------------------------------------------------------------------


async def test_tool_capable_client_is_given_the_declared_tools():
    client = _ToolCapableClient()
    agent = _agent_with(_DataProbeAgent, client)

    result = await agent.execute("Fetch data for SPY")

    names = [d["function"]["name"] for d in client.tools_requested]
    assert names == ["get_ohlcv"], f"agent was offered the wrong tools: {names}"
    assert result.success
    assert result.tool_calls_made == ["get_ohlcv"]
    assert agent.registry.dispatched == [("get_ohlcv", {"symbol": "SPY"})]


# ---------------------------------------------------------------------------
# Clients without tool support
# ---------------------------------------------------------------------------


async def test_data_agent_without_tool_support_does_not_report_success():
    """A tool-less client cannot fetch data, so the agent must not claim it did.

    This is the default path: the configured primary provider is MiniMax, whose
    client has no ``generate_with_tools``, so every agent used to return a
    confident-looking answer built from model memory with ``success=True``.
    """
    agent = _agent_with(_DataProbeAgent, _CompletionOnlyClient())

    result = await agent.execute("Fetch market data for SPY")

    assert not result.success, (
        "agent reported success without ever calling a tool -- the answer is "
        "model memory, not market data"
    )
    assert result.error, "a failed agent must say why"
    assert "generate_with_tools" in result.error
    assert "_CompletionOnlyClient" in result.error, "the error must name the client"


async def test_pure_reasoning_agent_without_tool_support_still_succeeds():
    """CritiqueAgent wants no data, so having no tools is not a failure for it."""
    agent = _agent_with(_ReasoningProbeAgent, _CompletionOnlyClient(content="The draft is thin."))

    result = await agent.execute("Critique this draft")

    assert result.success, "a tool-less pure-reasoning agent should still succeed"
    assert result.error is None
    assert result.content == "The draft is thin."


async def test_data_agent_without_tool_support_still_returns_the_model_text():
    """The text is kept for debugging, it just is not presented as a good result."""
    agent = _agent_with(_DataProbeAgent, _CompletionOnlyClient(content="SPY looks fine to me."))

    result = await agent.execute("Fetch market data for SPY")

    assert "SPY looks fine to me." in result.content


async def test_no_response_is_still_reported_as_a_failure():
    class _Silent(_CompletionOnlyClient):
        async def generate_completion(self, *args, **kwargs):
            return None

    agent = _agent_with(_DataProbeAgent, _Silent())

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
    agent = _agent_with(_DataProbeAgent, _ToolCapableClient(content=raw))

    result = await agent.execute("Analyse SPY")

    assert result.content.startswith("SPY closed at 601.20.")
    assert "<think>" not in result.content
    # The raw response is untouched -- only the surfaced text is cleaned.
    assert "<think>" in result.raw_response["choices"][0]["message"]["content"]
