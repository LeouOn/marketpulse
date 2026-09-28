"""Offline tests for the AI Trading Analyst (src/ai, pydantic-ai 2.x).

These tests never touch the network and never need an API key. pydantic-ai's
TestModel stands in for the LLM, and the Massive.com MCP server is only
constructed (never spawned) so its command/args/env stay asserted.
"""

from __future__ import annotations

import os

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from pydantic_ai.mcp import MCPToolset
from pydantic_ai.messages import ModelRequest, ModelResponse, TextPart, UserPromptPart
from pydantic_ai.models.function import FunctionModel
from pydantic_ai.models.test import TestModel

from src.ai.massive_analyst import MassiveAIAnalyst, TradingContext
from src.api.route_utils import route_entries

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def _no_ambient_keys(monkeypatch):
    """The analyst reads keys straight from os.environ; start from a clean slate."""
    for var in ("MASSIVE_API_KEY", "ANTHROPIC_API_KEY"):
        monkeypatch.delenv(var, raising=False)


def _settings(primary_provider: str = "minimax", **overrides):
    """Real LLMSettings with the provider bits pinned, so nothing leaks in from .env."""
    from src.core.config import get_settings

    settings = get_settings()
    settings.llm.model_routing.primary_provider = primary_provider
    for dotted, value in overrides.items():
        section, _, field = dotted.partition("__")
        setattr(getattr(settings.llm, section), field, value)
    return settings


def _analyst(**kwargs) -> MassiveAIAnalyst:
    """An analyst on a fake-keyed provider, so tests never touch a real endpoint."""
    return MassiveAIAnalyst(settings=_settings(minimax__api_key="minimax-key"), **kwargs)


@pytest.fixture
def anthropic_env(monkeypatch):
    """Kept for tests that assert the Anthropic path is no longer required."""
    return None


def _capture_model_requests(agent) -> list[ModelRequest]:
    """Swap in a FunctionModel that records every request, returning the list it fills."""
    requests: list[ModelRequest] = []

    def handler(messages, info):
        requests.extend(messages)
        return ModelResponse(parts=[TextPart("model reply")])

    agent.model = FunctionModel(handler)
    return requests


def _user_prompt_text(requests) -> str:
    return "\n".join(
        part.content
        for request in requests
        for part in request.parts
        if isinstance(part, UserPromptPart)
    )


# ---------------------------------------------------------------------------
# Construction
# ---------------------------------------------------------------------------


def test_analyst_requires_a_key_for_its_configured_provider():
    """No usable key for the provider it resolved -> refuse, and say which var to set."""
    settings = _settings("minimax", minimax__api_key="")

    with pytest.raises(ValueError, match="minimax API key required"):
        MassiveAIAnalyst(settings=settings)


def test_analyst_builds_without_massive_key():
    """A missing Massive.com key is not fatal — only the MCP toolset is lost."""
    analyst = _analyst()

    assert analyst.massive_api_key is None
    assert analyst.risk_manager is not None
    assert analyst.ict_analyzer is not None


def test_analyst_reads_the_massive_key_from_the_environment(monkeypatch):
    """The Massive key stays an env concern; only the LLM moved to app settings."""
    monkeypatch.setenv("MASSIVE_API_KEY", "env-massive-key")

    analyst = MassiveAIAnalyst(settings=_settings(minimax__api_key="minimax-key"))

    assert analyst.massive_api_key == "env-massive-key"


# ---------------------------------------------------------------------------
# MCP toolset wiring
# ---------------------------------------------------------------------------


def test_create_massive_mcp_server_returns_none_without_key():
    assert _analyst().create_massive_mcp_server() is None


def test_create_massive_mcp_server_preserves_command_args_and_env():
    """The MCP server must still be spawned the same way it was under pydantic-ai 1.x."""
    toolset = _analyst(massive_api_key="massive-key-123").create_massive_mcp_server()

    assert toolset is not None
    transport = toolset.client.transport
    assert transport.command == "uvx"
    assert transport.args == [
        "--from",
        "git+https://github.com/massive-com/mcp_massive@v0.4.0",
        "mcp_massive",
    ]
    assert transport.env["MASSIVE_API_KEY"] == "massive-key-123"


async def test_agent_registers_mcp_toolset_when_key_present(anthropic_env):
    analyst = _analyst(massive_api_key="massive-key-123")

    agent = await analyst.create_agent()

    toolsets = [t for t in agent.toolsets if isinstance(t, MCPToolset)]
    assert len(toolsets) == 1


async def test_agent_registers_no_mcp_toolset_without_key(anthropic_env):
    analyst = _analyst()

    agent = await analyst.create_agent()

    assert [t for t in agent.toolsets if isinstance(t, MCPToolset)] == []


async def test_agent_keeps_the_trading_analyst_system_prompt(anthropic_env):
    """The persona must reach the model, not just sit in the Agent.

    pydantic-ai 2.x silently ignores ``system_prompt=``, so this asserts on what
    the model is actually handed rather than on how the Agent was constructed.
    """
    analyst = _analyst()
    agent = await analyst.create_agent()
    requests = _capture_model_requests(agent)

    await analyst.query("Anything", include_technical_analysis=False)

    # Assert the persona reaches the model, not the mechanism used to carry it:
    # instructions= and system_prompt= both deliver it, by different routes.
    first = requests[0]
    delivered = " ".join(
        [str(first.instructions or "")]
        + [getattr(p, "content", "") for p in first.parts if hasattr(p, "content")]
    )
    assert "trading analyst" in delivered.lower()


# ---------------------------------------------------------------------------
# Querying
# ---------------------------------------------------------------------------


async def test_query_returns_model_output_without_network(anthropic_env):
    """A full query round-trip against TestModel: question in, model text out."""
    analyst = _analyst()
    agent = await analyst.create_agent()
    analyst.agent = agent
    analyst.agent.model = TestModel()

    answer = await analyst.query("How is AAPL performing?", include_technical_analysis=False)

    assert isinstance(answer, str)
    assert answer


async def test_query_records_conversation_history(anthropic_env):
    """Two questions in a row must both reach the model — history is the point."""
    analyst = _analyst()
    agent = await analyst.create_agent()
    analyst.agent = agent
    analyst.agent.model = TestModel()

    await analyst.query("First question", include_technical_analysis=False)
    await analyst.query("Second question", include_technical_analysis=False)

    # Two exchanges of user+assistant turns.
    assert len(analyst.message_history) == 4
    assert analyst.message_history[0]["content"] == "First question"
    assert analyst.message_history[2]["content"] == "Second question"


async def test_query_appends_technical_analysis_to_prompt(anthropic_env, monkeypatch):
    """With a symbol in hand, the analyst augments the prompt with local analysis."""
    analyst = _analyst()

    class _FakeYahoo:
        def get_bars(self, symbol, period=None, interval=None):
            import pandas as pd

            idx = pd.date_range("2024-01-01", periods=60, freq="D")
            prices = [100.0 + i for i in range(60)]
            # Match get_bars: a ticker level stays on the columns until flattened.
            columns = pd.MultiIndex.from_tuples(
                (field, symbol) for field in ("open", "high", "low", "close", "volume")
            )
            frame = pd.DataFrame(index=idx, columns=columns, dtype=float)
            frame[("open", symbol)] = prices
            frame[("high", symbol)] = [p + 2 for p in prices]
            frame[("low", symbol)] = [p - 2 for p in prices]
            frame[("close", symbol)] = prices
            frame[("volume", symbol)] = [1_000_000] * 60
            return frame

    monkeypatch.setattr("src.api.yahoo_client.YahooFinanceClient", _FakeYahoo)

    agent = await analyst.create_agent()
    analyst.agent = agent
    requests = _capture_model_requests(agent)

    await analyst.query("Should I buy AAPL?", include_technical_analysis=True)

    # The technical block is appended to the user prompt the model received.
    sent = _user_prompt_text(requests)
    assert "MarketPulse Technical Analysis for AAPL" in sent
    assert "Current Price:" in sent


async def test_query_reports_errors_instead_of_raising(anthropic_env):
    """A failing model must surface as an error string, not an exception."""
    analyst = _analyst()
    agent = await analyst.create_agent()
    analyst.agent = agent

    class _Boom(TestModel):
        async def request(self, *args, **kwargs):
            raise RuntimeError("model exploded")

    agent.model = _Boom()

    answer = await analyst.query("Anything", include_technical_analysis=False)

    assert answer.startswith("Error:")
    assert "model exploded" in answer


def test_validate_trade_returns_risk_manager_verdict():
    """Risk validation is local — it must work with no keys and no network."""
    import asyncio

    analyst = _analyst()

    verdict = asyncio.run(
        analyst.validate_trade(
            symbol="AAPL",
            entry_price=100.0,
            stop_loss=95.0,
            take_profit=115.0,
            direction="LONG",
            contracts=1,
        )
    )

    assert verdict["approved"] is True
    assert verdict["risk_metrics"]
    assert "suggested_contracts" in verdict


# ---------------------------------------------------------------------------
# API surface
# ---------------------------------------------------------------------------


@pytest.fixture
def status_client(monkeypatch):
    """A client for the AI router with the analyst singleton reset.

    monkeypatch (not plain assignment) so the previous value is restored at
    teardown: a cached analyst would otherwise leak into every later test in the
    session, answering /api/ai/* as if keys were configured.
    """
    from src.api import ai_endpoints

    monkeypatch.setattr(ai_endpoints, "analyst", None)
    app = FastAPI()
    app.include_router(ai_endpoints.ai_router)
    return TestClient(app, raise_server_exceptions=False)


def test_status_endpoint_reports_configured_state(status_client, monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "massive-key-123")

    response = status_client.get("/api/ai/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["provider_api_configured"] is True
    assert data["massive_api_configured"] is True
    assert data["features"]["massive_mcp_server"] is True


def test_status_client_restores_the_analyst_singleton(request, monkeypatch):
    """The fixture must RESTORE the previous value, not merely reset it to None.

    Resetting alone still leaks: a cached analyst from an earlier request would
    survive into every other test module that touches /api/ai, making those
    endpoints answer as if keys were configured.
    """
    from src.api import ai_endpoints

    sentinel = object()
    ai_endpoints.analyst = sentinel

    request.getfixturevalue("status_client")  # the fixture under test
    assert ai_endpoints.analyst is None, "fixture should clear the singleton while in use"

    monkeypatch.undo()  # exactly what pytest does at teardown
    assert ai_endpoints.analyst is sentinel, (
        "the fixture reset the singleton instead of restoring it -- the value "
        "leaks into every later test in the session"
    )


def test_ai_router_exposes_the_documented_endpoints(status_client):
    """The endpoint surface is part of the contract — pin the paths."""
    paths = {path for path, _methods in route_entries(status_client.app)}

    assert {
        "/api/ai/query",
        "/api/ai/query/{symbol}",
        "/api/ai/recommend",
        "/api/ai/recommend/{symbol}",
        "/api/ai/validate",
        "/api/ai/status",
        "/api/ai/",
    } <= paths


def test_trading_context_defaults():
    context = TradingContext(symbol="AAPL")

    assert context.symbol == "AAPL"
    assert context.risk_per_trade == 0.02


# ===========================================================================
# Provider selection: the analyst follows the app's configured default
# ===========================================================================


def test_analyst_uses_the_configured_primary_provider():
    """No Anthropic key involved: MiniMax is the configured default and it is used."""
    analyst = MassiveAIAnalyst(
        settings=_settings("minimax", minimax__api_key="minimax-key", minimax__model="MiniMax-M3")
    )

    assert analyst.provider.name == "minimax"
    assert analyst.provider.model == "MiniMax-M3"


def test_analyst_needs_no_anthropic_key(monkeypatch):
    """The old hard blocker is gone: a MiniMax key is enough to build the analyst."""
    monkeypatch.delenv("ANTHROPIC_API_KEY", raising=False)

    analyst = MassiveAIAnalyst(
        settings=_settings("minimax", minimax__api_key="minimax-key")
    )

    assert analyst.provider.api_key == "minimax-key"


def test_analyst_model_targets_the_configured_base_url():
    """The model must point at the provider's own host, not api.anthropic.com."""
    analyst = MassiveAIAnalyst(
        settings=_settings(
            "minimax", minimax__api_key="k", minimax__base_url="https://api.minimax.io/v1"
        )
    )

    assert analyst.model.base_url.startswith("https://api.minimax.io/v1")
    assert analyst.model.model_name == "MiniMax-M3"


def test_analyst_follows_a_different_configured_provider():
    """If the app's default changes, the analyst must follow it, not stay hard-coded."""
    analyst = MassiveAIAnalyst(
        settings=_settings("deepseek", deepseek__api_key="ds-key", deepseek__model_pro="deepseek-v4-pro")
    )

    assert analyst.provider.name == "deepseek"
    assert analyst.provider.model == "deepseek-v4-pro"
    assert analyst.model.base_url.startswith("https://api.deepseek.com")


def test_analyst_rejects_an_unknown_provider():
    with pytest.raises(ValueError, match="primary_provider"):
        MassiveAIAnalyst(settings=_settings("not-a-provider", minimax__api_key="k"))


@pytest.mark.parametrize(
    "provider,env_var",
    [("minimax", "MINIMAX_API_KEY"), ("deepseek", "DEEPSEEK_API_KEY")],
)
def test_missing_key_names_the_provider_and_its_env_var(provider, env_var):
    """The error must say which provider failed and which variable to set."""
    settings = _settings(provider)
    settings.llm.minimax.api_key = ""
    settings.llm.deepseek.api_key = ""

    with pytest.raises(ValueError) as exc:
        MassiveAIAnalyst(settings=settings)

    message = str(exc.value)
    assert provider in message
    assert env_var in message


def test_placeholder_key_is_treated_as_missing():
    settings = _settings("minimax", minimax__api_key="your_minimax_api_key")

    with pytest.raises(ValueError, match="MINIMAX_API_KEY"):
        MassiveAIAnalyst(settings=settings)


async def test_agent_runs_on_the_configured_model():
    """The agent is wired to the provider model, not to a Claude string."""
    analyst = MassiveAIAnalyst(
        settings=_settings("minimax", minimax__api_key="minimax-key")
    )

    agent = await analyst.create_agent()

    assert agent.model is analyst.model
    requests = _capture_model_requests(agent)
    await analyst.query("Anything", include_technical_analysis=False)
    assert requests, "the configured model should have been called"


# ===========================================================================
# /api/ai/status must describe the provider actually in use
# ===========================================================================


def test_status_reports_the_provider_in_use(status_client):
    from src.api import ai_endpoints

    analyst = MassiveAIAnalyst(
        settings=_settings("minimax", minimax__api_key="minimax-key")
    )
    ai_endpoints.analyst = analyst

    data = status_client.get("/api/ai/status").json()["data"]

    assert data["provider"] == "minimax"
    assert data["model"] == "MiniMax-M3"
    assert data["provider_api_configured"] is True


def test_status_works_without_an_anthropic_key(status_client):
    """The endpoint must not be dark when only the app's default provider is keyed."""
    data = status_client.get("/api/ai/status").json()["data"]

    assert data["provider"] == "minimax"
    assert data["provider_api_configured"] is True
    # Kept for anything still reading the old field.
    assert "anthropic_api_configured" in data


def test_status_explains_a_missing_key_for_the_configured_provider(status_client):
    """Same job as before -- name the variable to set -- but for the real provider."""
    from src.api import ai_endpoints

    ai_endpoints.analyst = None
    settings = _settings("minimax")
    settings.llm.minimax.api_key = ""
    settings.llm.deepseek.api_key = ""

    import src.core.config as config_mod

    original = config_mod.get_settings
    config_mod.get_settings = lambda: settings
    try:
        response = status_client.get("/api/ai/status")
    finally:
        config_mod.get_settings = original

    assert response.status_code == 500
    assert "minimax" in response.json()["detail"]
    assert "MINIMAX_API_KEY" in response.json()["detail"]


# ===========================================================================
# Live: the whole point of the switch is that it actually works
# ===========================================================================


_LIVE = os.getenv("RUN_LIVE_TESTS", "") == "1"
_skip_live = pytest.mark.skipif(not _LIVE, reason="Set RUN_LIVE_TESTS=1 to run live provider calls.")


@_skip_live
@pytest.mark.live
async def test_live_analyst_answers_on_the_configured_provider():
    """A real call on the app's default provider -- no Anthropic key anywhere."""
    from src.core.config import get_settings

    analyst = MassiveAIAnalyst(settings=get_settings())

    # query() builds the agent on first use, which is the real path.
    answer = await analyst.query("In one short sentence: what is a stop loss?", include_technical_analysis=False)

    assert isinstance(answer, str)
    assert answer.strip()
    assert "<think>" not in answer, "the answer leaked the model's inline reasoning"
    assert "API key required" not in answer


@_skip_live
@pytest.mark.live
async def test_live_analyst_can_call_a_tool():
    """Tool calling is the reason to switch: the Massive MCP data tools need it.

    The model comes from the analyst so this exercises the exact object the
    production endpoints use; only the toolset is supplied here, standing in for
    the Massive MCP server, which needs a key and a github.com fetch.
    """
    from pydantic_ai import Agent
    from pydantic_ai.toolsets.function import FunctionToolset

    from src.ai.massive_analyst import MassiveAIAnalyst
    from src.core.config import get_settings

    analyst = MassiveAIAnalyst(settings=get_settings())

    called = {}

    def get_quote(symbol: str) -> str:
        """Return the latest price for a symbol."""
        called["symbol"] = symbol
        return "SPY 601.20"

    toolset = FunctionToolset()
    toolset.tool_plain(get_quote)

    agent = Agent(analyst.model, toolsets=[toolset], instructions="You are a market analyst.")

    result = await agent.run("What is the latest price for SPY?")

    assert called.get("symbol") == "SPY", f"the model never called the tool (said: {result.output[:120]!r})"
    assert "601" in result.output
