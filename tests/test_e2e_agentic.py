"""Live end-to-end checks of the agentic pipeline.

This module used to be a manual script: the functions took ``settings``/``registry``
arguments that pytest read as fixtures (6 collection errors), they printed results
instead of asserting them, and the provider was hard-coded to DeepSeek even though
the configured primary provider is now MiniMax.

It is now an opt-in live test module::

    pytest tests/test_e2e_agentic.py -q                     # skipped
    RUN_LIVE_TESTS=1 pytest tests/test_e2e_agentic.py -q    # hits real providers

Everything here talks to real LLM providers, so it is skipped unless
``RUN_LIVE_TESTS=1``. Prompts are kept small and nothing loops.
"""

from __future__ import annotations

import os
import time

import pytest

# ---------------------------------------------------------------------------
# Live-test opt-in
# ---------------------------------------------------------------------------

_LIVE_ENABLED = os.getenv("RUN_LIVE_TESTS", "") == "1"
_SKIP_LIVE = pytest.mark.skipif(
    not _LIVE_ENABLED,
    reason="Set RUN_LIVE_TESTS=1 to run the live agentic pipeline (needs real LLM keys).",
)

# Small symbol list and one short question -- this is a smoke test, not a benchmark.
SYMBOL = "SPY"
QUERY = "Is SPY in an uptrend or showing warning signs?"


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def settings():
    """The app's settings singleton. Tests read providers from it, never hard-code one."""
    from src.core.config import get_settings

    return get_settings()


@pytest.fixture
def registry():
    from src.llm.tools import ToolRegistry

    return ToolRegistry()


# The DataAgent run is the most expensive step, so run it once and share the result
# between the data-agent and technical-agent tests.
_data_result = None


@pytest.fixture
async def data_result(settings, registry):
    global _data_result
    if _data_result is None:
        from src.llm.agents.data_agent import DataAgent

        async with DataAgent(registry=registry, settings=settings) as agent:
            _data_result = await agent.execute(
                f"Fetch market data for {SYMBOL}: market internals, breadth, "
                f"52-week stats, and 1 month of daily OHLCV."
            )
    return _data_result


# ---------------------------------------------------------------------------
# 1. Config
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
def test_config_exposes_a_usable_primary_provider(settings):
    """The configured primary provider must have a real key, not a placeholder."""
    routing = settings.llm.model_routing

    assert routing.primary_provider, "no primary_provider configured"

    key_blocks = {
        "minimax": settings.llm.minimax.api_key,
        "deepseek": settings.llm.deepseek.api_key,
    }
    key = key_blocks.get(routing.primary_provider)

    if key is not None:
        assert key, f"{routing.primary_provider} selected but its key is empty"
        assert "your_" not in key.lower(), f"{routing.primary_provider} key is still a placeholder"

    fallbacks = [p.strip() for p in routing.fallback_providers.split(",") if p.strip()]
    assert fallbacks, "no fallback providers configured"


# ---------------------------------------------------------------------------
# 2. Primary provider connectivity
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_primary_provider_completes_a_prompt(settings):
    """The provider the router actually picks must answer a trivial prompt."""
    from src.llm.model_router import ModelRouter

    async with ModelRouter(settings) as router:
        client, model_id = await router.route("fast")
        assert client is not None, "router returned no client"

        started = time.monotonic()
        response = await client.generate_completion(
            messages=[{"role": "user", "content": "Reply with exactly: OK"}],
            model=model_id or None,
            max_tokens=10,
            temperature=0.0,
        )
        elapsed = time.monotonic() - started

    assert response, f"{type(client).__name__} returned no response"
    assert "choices" in response, f"unexpected response shape: {list(response)}"

    content = response["choices"][0]["message"].get("content") or ""
    assert content.strip(), "provider returned an empty completion"
    print(f"\n{type(client).__name__} replied {content.strip()!r} in {elapsed:.1f}s")


# ---------------------------------------------------------------------------
# 3. ModelRouter
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_router_serves_every_capability(settings):
    """Every capability the agents ask for must resolve to a client and a model."""
    from src.llm.model_router import ModelRouter

    async with ModelRouter(settings) as router:
        routed = {}
        for capability in ("reasoning", "fast", "standard", "structured_output"):
            client, model_id = await router.route(capability)
            assert client is not None, f"no client for capability {capability}"
            routed[capability] = (type(client).__name__, model_id)

        models = router.list_available_models()

    assert len(routed) == 4
    assert models, "router reports no available models"


# ---------------------------------------------------------------------------
# 4. ToolRegistry
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_tool_registry_dispatches(registry):
    """The agents' tools must actually return data, not just be registered."""
    names = registry.get_tool_names()
    assert names, "tool registry is empty"

    active = await registry.dispatch("list_active_hypotheses", {})
    assert isinstance(active, dict)
    assert "error" not in active, f"list_active_hypotheses failed: {active}"

    found = await registry.dispatch("search_trading_knowledge", {"query": "fair value gap"})
    assert isinstance(found, dict)
    assert "error" not in found, f"search_trading_knowledge failed: {found}"


# ---------------------------------------------------------------------------
# 5. DataAgent
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_data_agent_uses_its_tools(data_result):
    """The DataAgent must reach real data, which means it must call tools."""
    assert data_result.error is None, f"DataAgent errored: {data_result.error}"
    assert data_result.success, "DataAgent reported failure"
    assert data_result.content.strip(), "DataAgent returned no content"
    assert data_result.tool_calls_made, (
        "DataAgent made no tool calls -- it answered from model knowledge only, "
        "so the data it returned is not real market data"
    )


# ---------------------------------------------------------------------------
# 6. TechnicalAgent
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_technical_agent_analyses_the_data(data_result, settings, registry):
    from src.llm.agents.technical_agent import TechnicalAgent

    data_context = data_result.content or "SPY data unavailable; describe what you would need."

    async with TechnicalAgent(registry=registry, settings=settings) as agent:
        result = await agent.execute(
            f"Run technical analysis on {SYMBOL} using this data:\n\n{data_context}\n\n"
            f"Analyse trend structure, key levels, and risk."
        )

    assert result.error is None, f"TechnicalAgent errored: {result.error}"
    assert result.content.strip(), "TechnicalAgent returned no content"
    assert result.tool_calls_made, (
        "TechnicalAgent made no tool calls -- the analysis is model opinion, "
        "not analysis of the supplied data"
    )


# ---------------------------------------------------------------------------
# 7. Full orchestrator
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_orchestrator_produces_a_synthesis(settings):
    """The full pipeline must return a plan, agent output, and a non-trivial synthesis."""
    from src.llm.agents.orchestrator import MarketAnalysisOrchestrator

    async with MarketAnalysisOrchestrator(settings) as orch:
        result = await orch.analyze(query=QUERY, symbols=[SYMBOL], include_breadth=True)

    assert result.plan, "orchestrator returned no plan"
    assert result.data_result is not None, "orchestrator ran no data agent"
    assert result.data_result.error is None, f"data agent errored: {result.data_result.error}"
    assert len(result.synthesis.strip()) > 20, "orchestrator produced no synthesis"

    # MiniMax-M3 returns its reasoning inline in content; that must not be the
    # whole answer.
    assert "<think>" not in result.synthesis or len(result.synthesis) > len(
        result.synthesis.split("</think>")[-1]
    ), "synthesis is nothing but inline reasoning"


# ---------------------------------------------------------------------------
# 8. Structured output (hypothesis tools)
# ---------------------------------------------------------------------------


@_SKIP_LIVE
@pytest.mark.live
async def test_structured_output_hypothesis_tools(registry):
    """Structured tools must return the fields the UI depends on."""
    detail = await registry.dispatch(
        "get_hypothesis_detail", {"hypothesis_name": "overnight_margin_cascade"}
    )

    assert "error" not in detail, f"get_hypothesis_detail failed: {detail}"
    assert detail.get("name"), "hypothesis detail has no name"
    assert detail.get("status"), "hypothesis detail has no status"
