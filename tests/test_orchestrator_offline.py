"""Offline tests for the orchestrator's synthesis text handling.

The orchestrator talks to the model directly (not through ``MarketAgent``), so it
needs its own coverage: MiniMax-M3 returns its reasoning inline in ``content``,
and the final synthesis is what the websocket pushes to the frontend.
"""

from __future__ import annotations

import pytest

from src.llm.agents.orchestrator import MarketAnalysisOrchestrator, OrchestratorResult


class _StubClient:
    def __init__(self, content: str):
        self._content = content

    async def generate_completion(self, messages, model=None, max_tokens=300, temperature=0.4):
        return {"choices": [{"message": {"content": self._content}}]}


class _StubRouter:
    def __init__(self, client):
        self._client = client

    async def route(self, capability):
        return self._client, "stub-model"


def _orchestrator_returning(content: str) -> MarketAnalysisOrchestrator:
    orch = MarketAnalysisOrchestrator.__new__(MarketAnalysisOrchestrator)
    orch._router = _StubRouter(_StubClient(content))
    orch._entered = True
    return orch


def _bare_result() -> OrchestratorResult:
    return OrchestratorResult(query="q")


# ---------------------------------------------------------------------------
# Inline reasoning must not reach the synthesis
# ---------------------------------------------------------------------------


async def test_draft_synthesis_has_no_leaked_reasoning():
    raw = "<think>Let me weigh the inputs.</think>\n\nSPY holds its 50-day."
    orch = _orchestrator_returning(raw)

    draft = await orch._synthesise_draft(_bare_result())

    assert draft.startswith("SPY holds its 50-day.")
    assert "<think>" not in draft


async def test_final_synthesis_has_no_leaked_reasoning():
    raw = "<think>Weighing again.</think>\n\nFinal: trend intact, stop below support."
    orch = _orchestrator_returning(raw)
    result = _bare_result()
    result.draft_synthesis = "draft"
    result.critique = "critique"

    final = await orch._synthesise_final(result)

    assert final.startswith("Final: trend intact, stop below support.")
    assert "<think>" not in final


async def test_synthesis_still_returns_plain_content_unchanged():
    orch = _orchestrator_returning("SPY holds its 50-day.")

    assert await orch._synthesise_draft(_bare_result()) == "SPY holds its 50-day."


# ---------------------------------------------------------------------------
# OrchestratorResult.success must reflect what actually happened
# ---------------------------------------------------------------------------


async def test_analyze_marks_failure_when_no_data_was_fetched(monkeypatch):
    """Every agent skipped is not a successful analysis."""
    from src.llm.agents import orchestrator as orch_mod

    class _NoToolDataAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, task, context=None):
            return orch_mod.AgentResult(
                agent_name="data_agent",
                content="SPY is fine.",
                success=False,
                error="MiniMaxClient does not support tool calling",
            )

    monkeypatch.setattr(orch_mod, "DataAgent", _NoToolDataAgent)
    async def _draft(self, result):
        return "draft from nothing"

    monkeypatch.setattr(MarketAnalysisOrchestrator, "_synthesise_draft", _draft)

    orch = MarketAnalysisOrchestrator.__new__(MarketAnalysisOrchestrator)
    orch.settings = object()
    orch._entered = True
    result = await orch.analyze(query="Is SPY healthy?", symbols=["SPY"], include_breadth=False)

    assert result.success is False
    assert result.error, "a failed pipeline must carry an error"
    assert "tool calling" in result.error


async def test_analyze_marks_success_when_data_was_fetched(monkeypatch):
    from src.llm.agents import orchestrator as orch_mod

    class _WorkingDataAgent:
        def __init__(self, *args, **kwargs):
            pass

        async def __aenter__(self):
            return self

        async def __aexit__(self, *exc):
            return False

        async def execute(self, task, context=None):
            return orch_mod.AgentResult(
                agent_name="data_agent",
                content="SPY OHLCV fetched.",
                success=True,
                tool_calls_made=["get_ohlcv"],
            )

    monkeypatch.setattr(orch_mod, "DataAgent", _WorkingDataAgent)
    async def _draft(self, result):
        return "draft"

    async def _dispatch(self, result, query, symbols, data_context):
        return None

    monkeypatch.setattr(MarketAnalysisOrchestrator, "_synthesise_draft", _draft)
    monkeypatch.setattr(MarketAnalysisOrchestrator, "_dispatch_agents", _dispatch)
    monkeypatch.setattr(
        orch_mod.CritiqueAgent,
        "execute",
        lambda self, task, context=None: _critique(),
    )

    orch = MarketAnalysisOrchestrator.__new__(MarketAnalysisOrchestrator)
    orch.settings = object()
    orch._entered = True
    result = await orch.analyze(query="Is SPY healthy?", symbols=["SPY"], include_breadth=False)

    assert result.success is True
    assert result.error is None


async def _critique():
    from src.llm.agents import orchestrator as orch_mod

    return orch_mod.AgentResult(agent_name="critique", content="Looks reasonable.", success=True)


@pytest.mark.parametrize("stream", [False])
def test_orchestrator_result_defaults_to_success(stream):
    """The dataclass default is optimistic; analyze() must correct it."""
    result = OrchestratorResult(query="q")

    assert result.success is True
    assert result.error is None
