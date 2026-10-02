"""Offline tests for the group-C agents: CritiqueAgent, OptionsFlowAgent, ICTSmartMoneyAgent.

Declarative ``MarketAgent`` subclasses; the tests pin their contracts (class
attributes, real-registry tool resolution, prompt contents) and their behaviour
through ``MarketAgent.execute()`` with faked clients/router — same style as
``tests/test_agents_group_a.py`` / ``test_agents_group_b.py``. No LLM, no
network, no sockets; every call is a direct in-process await (nothing can hang).

CritiqueAgent is the fleet's only tool-less agent: for it, a client without
``generate_with_tools`` is NOT a failure (``expects_tools`` is false), which is
pinned here explicitly.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from src.llm.agents import CritiqueAgent, ICTSmartMoneyAgent, OptionsFlowAgent
from src.llm.agents.base import MarketAgent

AGENTS = [CritiqueAgent, OptionsFlowAgent, ICTSmartMoneyAgent]

AGENT_NAMES = {
    CritiqueAgent: "critique_agent",
    OptionsFlowAgent: "options_agent",
    ICTSmartMoneyAgent: "ict_agent",
}

EXPECTED_TOOLS = {
    CritiqueAgent: [],
    OptionsFlowAgent: ["screen_options_flow", "compute_indicators"],
    ICTSmartMoneyAgent: ["generate_ict_signals", "analyze_order_flow", "detect_divergences"],
}

ALL_AGENT_TOOLS = sorted({name for names in EXPECTED_TOOLS.values() for name in names})


def _defn(name: str) -> dict:
    return {
        "type": "function",
        "function": {"name": name, "description": f"Fake {name}.", "parameters": {"type": "object", "properties": {}}},
    }


class _FakeRegistry:
    def __init__(self, definitions=None):
        self._definitions = definitions if definitions is not None else [_defn(n) for n in ALL_AGENT_TOOLS]
        self.dispatched: list[tuple[str, dict]] = []

    def list_definitions(self, names):
        wanted = set(names or ())
        return [d for d in self._definitions if d["function"]["name"] in wanted]

    def get_tool_names(self):
        return [d["function"]["name"] for d in self._definitions]

    async def dispatch(self, name, args):
        self.dispatched.append((name, args))
        return {"ok": True, "tool": name}


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
    def __init__(self, content="Generic answer."):
        self._content = content
        self.calls: list[dict] = []

    async def generate_completion(self, messages, model=None, max_tokens=300, temperature=0.3):
        self.calls.append({"messages": messages, "max_tokens": max_tokens, "temperature": temperature})
        return {"choices": [{"message": {"content": self._content}}]}


class _ToolCapableClient:
    def __init__(self, content="Final analysis.", first_tool="screen_options_flow"):
        self._content = content
        self._first_tool = first_tool
        self.messages = None
        self.tools_requested = None
        self.kwargs = None

    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        self.messages = messages
        self.tools_requested = tools
        self.kwargs = {"max_turns": max_turns, "max_tokens": max_tokens, "temperature": temperature}
        if self._first_tool:
            await tool_handler(self._first_tool, {"symbol": "SPY"})
        return {"choices": [{"message": {"content": self._content}}]}


class _SilentClient(_ToolCapableClient):
    """Returns a response dict without any choices."""

    def __init__(self):
        super().__init__(content="")

    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        return {"error": "empty"}


class _CrashClient(_ToolCapableClient):
    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        raise RuntimeError("provider exploded")


def _agent(cls, client) -> MarketAgent:
    registry = _FakeRegistry()
    agent = cls(registry=registry, settings=object())
    agent._router = _FakeRouter(client)
    agent._entered = True
    agent._test_registry = registry
    return agent


def _run(coro):
    return asyncio.run(coro)


# ---------------------------------------------------------------------------
# Class contract
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_class_contract(cls):
    assert cls.AGENT_NAME == AGENT_NAMES[cls]
    assert isinstance(cls.SYSTEM_PROMPT, str) and len(cls.SYSTEM_PROMPT) > 100
    assert cls.CAPABILITY in ("reasoning", "fast", "standard")
    assert isinstance(cls.MAX_TOKENS, int) and cls.MAX_TOKENS > 0
    assert isinstance(cls.MAX_TURNS, int) and cls.MAX_TURNS >= 1
    assert 0.0 <= cls.TEMPERATURE <= 2.0
    assert cls.TOOL_NAMES == EXPECTED_TOOLS[cls]
    assert len(cls.TOOL_NAMES) == len(set(cls.TOOL_NAMES))


@pytest.mark.parametrize("cls", [OptionsFlowAgent, ICTSmartMoneyAgent], ids=lambda c: AGENT_NAMES[c])
def test_declared_tools_resolve_in_the_real_registry(cls):
    from src.llm.tools import ToolRegistry

    registry = ToolRegistry()
    resolved = [d["function"]["name"] for d in registry.list_definitions(cls.TOOL_NAMES)]
    assert sorted(resolved) == sorted(cls.TOOL_NAMES)


@pytest.mark.parametrize("cls", [OptionsFlowAgent, ICTSmartMoneyAgent], ids=lambda c: AGENT_NAMES[c])
def test_prompt_mentions_the_agents_own_tools(cls):
    for name in cls.TOOL_NAMES:
        assert name in cls.SYSTEM_PROMPT, f"{AGENT_NAMES[cls]} prompt never mentions its tool {name!r}"


def test_critique_agent_is_the_pure_reasoning_agent():
    assert CritiqueAgent.TOOL_NAMES == []
    # It never mentions fetching data: nothing in the prompt tells the model to call tools.
    for tool in ("get_ohlcv", "screen_options_flow", "generate_ict_signals"):
        assert tool not in CritiqueAgent.SYSTEM_PROMPT
    # And an empty tool list resolves to an empty definition list.
    assert _FakeRegistry().list_definitions(CritiqueAgent.TOOL_NAMES) == []


# ---------------------------------------------------------------------------
# execute() wiring
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", [OptionsFlowAgent, ICTSmartMoneyAgent], ids=lambda c: AGENT_NAMES[c])
def test_execute_with_tool_capable_client(cls):
    client = _ToolCapableClient(content="Flow looks unusual.")
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY"))

    assert result.agent_name == AGENT_NAMES[cls]
    assert result.success is True and result.error is None
    assert result.content == "Flow looks unusual."
    assert agent._test_registry.dispatched and agent._test_registry.dispatched[0][0] == client._first_tool
    offered = sorted(d["function"]["name"] for d in client.tools_requested)
    assert offered == sorted(cls.TOOL_NAMES)
    assert client.kwargs["max_tokens"] == cls.MAX_TOKENS
    assert client.kwargs["temperature"] == cls.TEMPERATURE


def test_execute_critique_with_toolless_client_is_a_success():
    """CritiqueAgent never wanted data, so a completion-only client is fine."""
    client = _CompletionOnlyClient(content="The draft overclaims.")
    agent = _agent(CritiqueAgent, client)

    result = _run(agent.execute("Critique this draft"))

    assert result.success is True
    assert result.error is None
    assert result.content == "The draft overclaims."


def test_execute_critique_with_tool_capable_client_offers_no_tools():
    client = _ToolCapableClient(content="Still a critique.", first_tool=None)
    agent = _agent(CritiqueAgent, client)

    result = _run(agent.execute("Critique this draft"))

    assert result.success is True
    assert client.tools_requested == []


@pytest.mark.parametrize("cls", [OptionsFlowAgent, ICTSmartMoneyAgent], ids=lambda c: AGENT_NAMES[c])
def test_execute_toolless_client_reports_unverified(cls):
    client = _CompletionOnlyClient(content="Answer from memory.")
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY"))

    assert result.success is False
    assert AGENT_NAMES[cls] in result.error
    assert "generate_with_tools" in result.error
    assert result.content == "Answer from memory."


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_strips_inline_think_block(cls):
    client = _ToolCapableClient(content="<think>reasoning</think>The real answer.", first_tool=None)
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY"))

    assert result.content == "The real answer."


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_survives_an_empty_task(cls):
    client = _ToolCapableClient(content="Done.", first_tool=None)
    agent = _agent(cls, client)

    result = _run(agent.execute(""))

    assert result.success is True
    assert client.messages[1]["content"] == ""


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_injects_context_with_none_and_nan(cls):
    client = _ToolCapableClient(first_tool=None)
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY", context={"note": None, "score": math.nan, "list": [1, None]}))

    assert result.success is True
    system = client.messages[0]["content"]
    assert system.startswith(cls.SYSTEM_PROMPT)
    assert "ADDITIONAL CONTEXT:" in system
    assert "NaN" in system


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_client_crash_is_reported_not_raised(cls):
    agent = _agent(cls, _CrashClient())

    result = _run(agent.execute("Analyze SPY"))

    assert result.success is False
    assert result.error == "provider exploded"


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_silent_client_is_a_failure(cls):
    agent = _agent(cls, _SilentClient())

    result = _run(agent.execute("Analyze SPY"))

    assert result.success is False
    assert result.content == ""


def test_execute_requires_enter_options():
    agent = OptionsFlowAgent(registry=_FakeRegistry(), settings=object())
    with pytest.raises(RuntimeError, match="not entered"):
        _run(agent.execute("Analyze SPY"))


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_construction_filters_registry_to_declared_tools(cls):
    agent = cls(registry=_FakeRegistry(), settings=object())
    names = [d["function"]["name"] for d in agent._tools]
    assert sorted(names) == sorted(cls.TOOL_NAMES)
