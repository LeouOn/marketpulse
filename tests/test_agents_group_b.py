"""Offline tests for the group-B agents: RiskAgent, MacroAgent, RiskQuantAgent.

These are declarative ``MarketAgent`` subclasses; the tests pin their
contracts (class attributes, real-registry tool resolution, prompt contents)
and their behaviour through ``MarketAgent.execute()`` with faked
clients/router — same style as tests/test_agents_offline.py. No LLM, no
network.
"""

from __future__ import annotations

import pytest

from src.llm.agents.base import MarketAgent
from src.llm.agents.macro_agent import MacroAgent
from src.llm.agents.risk_agent import RiskAgent
from src.llm.agents.risk_quant_agent import RiskQuantAgent

AGENTS = [RiskAgent, MacroAgent, RiskQuantAgent]

# The regime names classify_regime actually returns (its branch matrix is
# pinned in tests/test_upstream_tools.py).
REAL_REGIMES = ["TRENDING_BULLISH", "TRENDING_BEARISH", "RANGE_BOUND", "CHOPPY_AVOID", "BREAKOUT_PENDING"]

_TOOL_TEMPLATE = {
    "type": "function",
    "function": {
        "name": "placeholder",
        "description": "fake",
        "parameters": {"type": "object", "properties": {}},
    },
}


def _defs(*names):
    out = []
    for name in names:
        definition = {"type": "function", "function": dict(_TOOL_TEMPLATE["function"], name=name)}
        out.append(definition)
    return out


ALL_AGENT_TOOLS = _defs(
    "get_ohlcv",
    "get_symbol_52w_stats",
    "get_market_internals",
    "get_breadth",
    "calculate_risk_metrics",
    "classify_regime",
)


class _FakeRegistry:
    def __init__(self, definitions=ALL_AGENT_TOOLS):
        self._definitions = list(definitions)
        self.dispatched: list[tuple[str, dict]] = []

    def list_definitions(self, names):
        wanted = set(names or ())
        return [d for d in self._definitions if d["function"]["name"] in wanted]

    def get_tool_names(self):
        return [d["function"]["name"] for d in self._definitions]

    async def dispatch(self, name, args):
        self.dispatched.append((name, args))
        return {"ok": True, "for": name}


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
    """A client like MiniMaxClient pre-cycle2: no generate_with_tools."""

    def __init__(self, content="Risk is manageable."):
        self._content = content
        self.messages = None

    async def generate_completion(self, messages, model=None, max_tokens=300, temperature=0.3):
        self.messages = messages
        return {"choices": [{"message": {"content": self._content}}]}


class _ToolCapableClient(_CompletionOnlyClient):
    def __init__(self, content="Quant risk is fine.", tool_name="get_ohlcv"):
        super().__init__(content)
        self._tool_name = tool_name
        self.tools_requested = None
        self.saw_messages = None

    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        self.tools_requested = tools
        self.saw_messages = list(messages)
        await tool_handler(self._tool_name, {"symbol": "SPY"})
        return {"choices": [{"message": {"content": self._content}}]}


class _RaisingClient:
    async def generate_with_tools(self, *args, **kwargs):
        raise RuntimeError("provider exploded")


class _SilentClient:
    async def generate_with_tools(self, *args, **kwargs):
        return None


def _agent_with(agent_cls: type[MarketAgent], client) -> MarketAgent:
    agent = agent_cls(registry=_FakeRegistry(), settings=object())
    agent._router = _FakeRouter(client)
    agent._entered = True
    return agent


def _first_tool_of(agent_cls) -> str:
    return agent_cls.TOOL_NAMES[0]


# ---------------------------------------------------------------------------
# Declarative contracts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
def test_agent_class_contract(agent_cls):
    assert agent_cls.AGENT_NAME
    assert agent_cls.CAPABILITY == "reasoning"
    assert agent_cls.MAX_TOKENS == 800
    assert agent_cls.SYSTEM_PROMPT.strip()
    assert agent_cls.TOOL_NAMES, "these agents are data-driven; empty TOOL_NAMES would be a regression"


def test_agent_specific_attributes():
    assert RiskAgent.TEMPERATURE == 0.3
    assert RiskAgent.TOOL_NAMES == ["get_ohlcv", "get_symbol_52w_stats"]
    assert MacroAgent.TEMPERATURE == 0.3
    assert MacroAgent.TOOL_NAMES == ["get_market_internals", "get_breadth"]
    assert RiskQuantAgent.TEMPERATURE == 0.2
    assert RiskQuantAgent.TOOL_NAMES == ["calculate_risk_metrics", "classify_regime"]


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
def test_declared_tools_resolve_in_the_real_registry(agent_cls):
    """A renamed tool would silently gut the agent; the registry must know
    every name the agent declares."""
    agent = agent_cls()  # real ToolRegistry + real settings; offline

    resolved = {d["function"]["name"] for d in agent._tools}
    assert resolved == set(agent_cls.TOOL_NAMES), (
        f"{agent_cls.__name__} declares tools the registry does not provide: {set(agent_cls.TOOL_NAMES) - resolved}"
    )


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
def test_prompt_mentions_the_agents_own_tools(agent_cls):
    for tool_name in agent_cls.TOOL_NAMES:
        assert tool_name in agent_cls.SYSTEM_PROMPT, (
            f"{agent_cls.__name__} prompt never mentions its tool {tool_name!r}"
        )


def test_risk_quant_prompt_uses_the_real_regime_taxonomy():
    """The prompt must enumerate the regime names classify_regime returns."""
    for regime in REAL_REGIMES:
        assert regime in RiskQuantAgent.SYSTEM_PROMPT, f"prompt is missing the real regime {regime!r}"


# ---------------------------------------------------------------------------
# execute() behaviour through base.py (faked client/router)
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_with_tool_capable_client(agent_cls):
    client = _ToolCapableClient(tool_name=_first_tool_of(agent_cls))
    agent = _agent_with(agent_cls, client)

    result = await agent.execute("Assess SPY")

    assert result.success is True
    assert result.agent_name == agent_cls.AGENT_NAME
    assert result.content == "Quant risk is fine."
    assert result.error is None
    # The agent's declared tools (and only those) were offered to the model.
    offered = [d["function"]["name"] for d in client.tools_requested]
    assert set(offered) == set(agent_cls.TOOL_NAMES)
    # The tool call flowed through the handler to the registry.
    assert result.tool_calls_made == [_first_tool_of(agent_cls)]


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_prompt_carries_system_task_and_context(agent_cls):
    client = _ToolCapableClient(tool_name=_first_tool_of(agent_cls))
    agent = _agent_with(agent_cls, client)

    await agent.execute("Assess SPY", context={"note": "VIX spiked overnight"})

    system = client.saw_messages[0]
    assert system["role"] == "system"
    assert agent_cls.SYSTEM_PROMPT in system["content"]
    assert "ADDITIONAL CONTEXT" in system["content"]
    assert "VIX spiked overnight" in system["content"]
    assert client.saw_messages[1] == {"role": "user", "content": "Assess SPY"}


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_without_tool_support_reports_failure_but_keeps_text(agent_cls):
    """All three agents expect data; a tool-less client must not read as success."""
    client = _CompletionOnlyClient(content="Best guess from memory.")
    agent = _agent_with(agent_cls, client)

    result = await agent.execute("Assess SPY")

    assert result.success is False
    assert "does not support tool calling" in result.error
    assert result.content == "Best guess from memory."


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_survives_an_empty_task(agent_cls):
    client = _ToolCapableClient(tool_name=_first_tool_of(agent_cls))
    agent = _agent_with(agent_cls, client)

    result = await agent.execute("")

    assert result.success is True
    assert client.saw_messages[1]["content"] == ""


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_strips_inline_think_blocks(agent_cls):
    client = _ToolCapableClient(
        content="<think>reasoning here</think>Visible answer.", tool_name=_first_tool_of(agent_cls)
    )
    agent = _agent_with(agent_cls, client)

    result = await agent.execute("Assess SPY")

    assert result.content == "Visible answer."


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_client_crash_is_reported_not_raised(agent_cls):
    agent = _agent_with(agent_cls, _RaisingClient())

    result = await agent.execute("Assess SPY")

    assert result.success is False
    assert "provider exploded" in result.error
    assert result.content == ""


@pytest.mark.parametrize("agent_cls", AGENTS, ids=lambda c: c.__name__)
async def test_execute_silent_client_is_a_failure(agent_cls):
    agent = _agent_with(agent_cls, _SilentClient())

    result = await agent.execute("Assess SPY")

    assert result.success is False
    assert "No response from model" in result.error
