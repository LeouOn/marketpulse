"""Offline coverage for the group-A agents (cycle 12):

* ``src/llm/agents/multi_tf_agent.py``   (MultiTFAgent)
* ``src/llm/agents/strategy_agent.py``  (StrategyProposalAgent)
* ``src/llm/agents/hypothesis_agent.py`` (HypothesisAgent)

These are declarative ``MarketAgent`` subclasses (system prompt + tool list +
model knobs; all behaviour inherited from ``src/llm/agents/base.py``). The
tests therefore pin the CONTRACT: tool lists resolve against the real
``ToolRegistry``, the class knobs are sane, prompts reference their own tools,
and ``execute()`` is wired correctly per agent (tool-capable client, tool-less
client, <think> stripping, tool-calls-without-text, client failure, context
injection incl. None/NaN values).

Style and fakes follow ``tests/test_agents_offline.py``: fake registry/router/
clients injected directly, no provider, no network.
"""

from __future__ import annotations

import asyncio
import math

import pytest

from src.llm.agents import HypothesisAgent, MultiTFAgent, StrategyProposalAgent
from src.llm.agents.base import MarketAgent

AGENTS = [MultiTFAgent, StrategyProposalAgent, HypothesisAgent]

ALL_TOOL_NAMES = sorted({name for cls in AGENTS for name in cls.TOOL_NAMES})

EXPECTED_TOOLS = {
    MultiTFAgent: ["get_ohlcv", "analyze_symbol_technicals", "find_support_resistance"],
    StrategyProposalAgent: ["run_backtest", "generate_ict_signals", "detect_divergences", "calculate_risk_metrics"],
    HypothesisAgent: ["list_active_hypotheses", "get_hypothesis_detail", "get_ohlcv"],
}

AGENT_NAMES = {
    MultiTFAgent: "multi_tf_agent",
    StrategyProposalAgent: "strategy_agent",
    HypothesisAgent: "hypothesis_agent",
}


# ---------------------------------------------------------------------------
# Fakes (test_agents_offline.py style)
# ---------------------------------------------------------------------------


def _defn(name: str) -> dict:
    return {
        "type": "function",
        "function": {
            "name": name,
            "description": f"Fake {name}.",
            "parameters": {"type": "object", "properties": {}},
        },
    }


class _FakeRegistry:
    def __init__(self, definitions=None):
        self._definitions = definitions or [_defn(n) for n in ALL_TOOL_NAMES]
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
    """Like MiniMaxClient pre-tools: plain completions only."""

    def __init__(self, content="Generic answer."):
        self._content = content
        self.messages = None

    async def generate_completion(self, messages, model=None, max_tokens=300, temperature=0.3):
        self.messages = messages
        return {"choices": [{"message": {"content": self._content}}]}


class _ToolCapableClient:
    """Like DeepSeekClient / MiniMaxClient.generate_with_tools."""

    def __init__(self, content="Final analysis text.", first_tool="get_ohlcv"):
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
        self.kwargs = {"max_turns": max_turns, "max_tokens": max_tokens, "temperature": temperature, "model": model}
        await tool_handler(self._first_tool, {"symbol": "SPY"})
        return {"choices": [{"message": {"content": self._content}}]}


class _NoTextToolClient(_ToolCapableClient):
    """Calls a tool, returns no final text."""

    def __init__(self, first_tool="get_ohlcv"):
        super().__init__(content="", first_tool=first_tool)

    async def generate_with_tools(
        self, messages, tools, tool_handler, model=None, max_turns=5, max_tokens=800, temperature=0.3
    ):
        await tool_handler(self._first_tool, {"symbol": "SPY"})
        return {"choices": [{"message": {"content": "", "tool_calls": [{"id": "1"}]}}]}


class _RaisingToolClient(_ToolCapableClient):
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
# Class contract: knobs, tool lists, prompts
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_class_knobs_are_sane(cls):
    assert cls.AGENT_NAME == AGENT_NAMES[cls]
    assert isinstance(cls.SYSTEM_PROMPT, str) and len(cls.SYSTEM_PROMPT) > 100
    assert cls.CAPABILITY in ("reasoning", "fast", "standard")
    assert isinstance(cls.MAX_TOKENS, int) and cls.MAX_TOKENS > 0
    assert isinstance(cls.MAX_TURNS, int) and cls.MAX_TURNS >= 1
    assert 0.0 <= cls.TEMPERATURE <= 2.0
    assert cls.TOOL_NAMES == EXPECTED_TOOLS[cls]
    assert len(cls.TOOL_NAMES) == len(set(cls.TOOL_NAMES)), "duplicate tool names"


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_every_declared_tool_resolves_in_the_real_registry(cls):
    """A name the registry does not know is silently dropped by
    ``list_definitions`` — the agent would lose a tool its prompt relies on."""
    from src.llm.tools import ToolRegistry

    registry = ToolRegistry()  # offline: only collects defs/handlers
    resolved = [d["function"]["name"] for d in registry.list_definitions(cls.TOOL_NAMES)]
    assert sorted(resolved) == sorted(cls.TOOL_NAMES), (
        f"{AGENT_NAMES[cls]}: TOOL_NAMES not all registered; resolved={resolved}"
    )


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_prompt_references_every_declared_tool(cls):
    for name in cls.TOOL_NAMES:
        assert name in cls.SYSTEM_PROMPT, f"{AGENT_NAMES[cls]} prompt never mentions its tool {name!r}"


def test_agent_names_are_unique_across_the_fleet():
    import importlib
    import pkgutil

    import src.llm.agents as pkg

    seen: dict[str, str] = {}
    for mod_info in pkgutil.iter_modules(pkg.__path__):
        if mod_info.name in ("base", "orchestrator", "__init__"):
            continue
        module = importlib.import_module(f"src.llm.agents.{mod_info.name}")
        for attr in dir(module):
            obj = getattr(module, attr)
            if (
                isinstance(obj, type)
                and issubclass(obj, MarketAgent)
                and obj is not MarketAgent
                and obj.__module__ == module.__name__
            ):
                name = getattr(obj, "AGENT_NAME", None)
                if not name or name == "base":
                    continue
                assert name not in seen, f"duplicate AGENT_NAME {name!r} in {mod_info.name} and {seen[name]}"
                seen[name] = mod_info.name
    assert AGENT_NAMES[MultiTFAgent] in seen
    assert AGENT_NAMES[StrategyProposalAgent] in seen
    assert AGENT_NAMES[HypothesisAgent] in seen


# ---------------------------------------------------------------------------
# execute() wiring per agent
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_with_tool_capable_client(cls):
    client = _ToolCapableClient(content="Confluence looks strong.")
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY"))

    assert result.agent_name == AGENT_NAMES[cls]
    assert result.success is True
    assert result.error is None
    assert result.content == "Confluence looks strong."
    assert result.tool_calls_made == ["get_ohlcv"]
    assert agent._test_registry.dispatched == [("get_ohlcv", {"symbol": "SPY"})]
    # The agent offered exactly its declared tools, with its knobs forwarded.
    offered = sorted(d["function"]["name"] for d in client.tools_requested)
    assert offered == sorted(cls.TOOL_NAMES)
    assert client.kwargs["max_tokens"] == cls.MAX_TOKENS
    assert client.kwargs["temperature"] == cls.TEMPERATURE
    assert client.kwargs["max_turns"] == cls.MAX_TURNS


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_with_toolless_client_reports_unverified(cls):
    client = _CompletionOnlyClient(content="Answer from memory.")
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY"))

    # These agents all expect data, so a tool-less answer must not read as success.
    assert result.success is False
    assert AGENT_NAMES[cls] in result.error
    assert "generate_with_tools" in result.error
    assert result.content == "Answer from memory."


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_strips_inline_think_block(cls):
    client = _ToolCapableClient(content="<think>chain of thought</think>The real answer.")
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY"))

    assert result.content == "The real answer."


def test_execute_with_tools_but_no_final_text_hypothesis():
    client = _NoTextToolClient(first_tool="list_active_hypotheses")
    agent = _agent(HypothesisAgent, client)

    result = _run(agent.execute("Check hypotheses"))

    assert result.tool_calls_made == ["list_active_hypotheses"]
    assert "list_active_hypotheses" in result.content
    assert "no final text" in result.content


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_client_failure_is_a_clean_error(cls):
    agent = _agent(cls, _RaisingToolClient())

    result = _run(agent.execute("Analyze SPY"))

    assert result.success is False
    assert result.error == "provider exploded"
    assert result.content == ""


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_execute_injects_context_with_none_and_nan(cls):
    client = _ToolCapableClient()
    agent = _agent(cls, client)

    result = _run(agent.execute("Analyze SPY", context={"note": None, "score": math.nan, "nested": {"a": 1}}))

    assert result.success is True
    system = client.messages[0]["content"]
    assert system.startswith(cls.SYSTEM_PROMPT)
    assert "ADDITIONAL CONTEXT:" in system
    assert "NaN" in system  # _fmt degrades NaN via json.dumps default semantics
    assert result.raw_response is not None


def test_execute_requires_enter_multi_tf():
    agent = MultiTFAgent(registry=_FakeRegistry(), settings=object())
    with pytest.raises(RuntimeError, match="not entered"):
        _run(agent.execute("Analyze SPY"))


@pytest.mark.parametrize("cls", AGENTS, ids=lambda c: AGENT_NAMES[c])
def test_construction_filters_registry_to_declared_tools(cls):
    registry = _FakeRegistry()
    agent = cls(registry=registry, settings=object())
    names = [d["function"]["name"] for d in agent._tools]
    assert sorted(names) == sorted(cls.TOOL_NAMES)
