"""Offline tests for the AI Trading Analyst (src/ai, pydantic-ai 2.x).

These tests never touch the network and never need an API key. pydantic-ai's
TestModel stands in for the LLM, and the Massive.com MCP server is only
constructed (never spawned) so its command/args/env stay asserted.
"""

from __future__ import annotations

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


def _analyst(**kwargs) -> MassiveAIAnalyst:
    return MassiveAIAnalyst(anthropic_api_key="test-anthropic-key", **kwargs)


@pytest.fixture
def anthropic_env(monkeypatch):
    """pydantic-ai builds the Anthropic provider eagerly, so the key must be in the env."""
    monkeypatch.setenv("ANTHROPIC_API_KEY", "test-anthropic-key")
    return "test-anthropic-key"


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


def test_analyst_requires_anthropic_key():
    """Without an Anthropic key the analyst refuses to build, naming the env var."""
    with pytest.raises(ValueError, match="Anthropic API key required"):
        MassiveAIAnalyst()


def test_analyst_builds_without_massive_key():
    """A missing Massive.com key is not fatal — only the MCP toolset is lost."""
    analyst = _analyst()

    assert analyst.massive_api_key is None
    assert analyst.risk_manager is not None
    assert analyst.ict_analyzer is not None


def test_analyst_reads_keys_from_environment(monkeypatch):
    """Keys may come from the environment instead of constructor arguments."""
    monkeypatch.setenv("MASSIVE_API_KEY", "env-massive-key")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "env-anthropic-key")

    analyst = MassiveAIAnalyst()

    assert analyst.massive_api_key == "env-massive-key"
    assert analyst.anthropic_api_key == "env-anthropic-key"


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


def test_status_endpoint_explains_the_missing_anthropic_key(status_client):
    """`/api/ai/status` must tell the operator exactly which key is missing."""
    response = status_client.get("/api/ai/status")

    assert response.status_code == 500
    assert "Anthropic API key required" in response.json()["detail"]


def test_status_endpoint_reports_configured_state(status_client, monkeypatch):
    monkeypatch.setenv("MASSIVE_API_KEY", "massive-key-123")
    monkeypatch.setenv("ANTHROPIC_API_KEY", "anthropic-key-123")

    response = status_client.get("/api/ai/status")

    assert response.status_code == 200
    data = response.json()["data"]
    assert data["anthropic_api_configured"] is True
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
