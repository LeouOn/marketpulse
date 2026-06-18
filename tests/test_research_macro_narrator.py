"""Tests for ``src/research/macro/narrator.py`` (LLMJudgeNarrator, W3/T13).

Covers the 8 required scenarios from the W3/T13 spec, all using a mocked
:class:`ModelRouter` so no network call is made:

  1. Happy path -- mock returns valid JSON; RegimeJudgeOutput parsed correctly
     and ModelRouter.generate called exactly once.
  2. Probabilities sum validator -- mock returns probs summing to 0.5;
     retry also fails -> LLMJudgeError (we assert the validator fires).
  3. Malformed JSON triggers retry -- first response is garbage, second
     is valid; ModelRouter.generate called twice; happy output returned.
  4. Cache hit -- pre-populate cache; no ModelRouter.generate call.
  5. Cache TTL expired -- stale cache entry triggers refetch.
  6. Async behaviour -- ``judge_and_narrate`` returns an awaitable.
  7. Fed statements stub -- empty string works (graceful degradation).
  8. Second failure raises LLMJudgeError -- both attempts fail.

Also includes direct unit tests on :class:`RegimeJudgeOutput`:

  9. Validator accepts probs summing to exactly 1.0 and within tolerance.
 10. Validator rejects probs summing to 0.5 OR 1.5 OR out-of-range values.
"""

from __future__ import annotations

import asyncio
import inspect
import json
from datetime import date, datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock

import pandas as pd
import pytest
from pydantic import ValidationError

from src.research.data import AssetConfig
from src.research.macro.narrator import (
    LLMJudgeError,
    LLMJudgeNarrator,
    Regime,
    RegimeJudgeOutput,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _good_response(
    probs: dict[str, float] | None = None,
    narrative: str | None = None,
) -> dict:
    """Build an OpenAI-style choices response wrapping a JSON string."""
    payload = {
        "regime_probs": probs
        or {
            "RISK_ON": 0.40,
            "DEFLATION_SCARE": 0.15,
            "INFLATION_ACCEL": 0.15,
            "REAL_YIELD_SHOCK": 0.10,
            "RECESSION": 0.20,
        },
        "narrative": narrative
        or (
            "The current factor mix echoes the Q4 2018 selloff: rising real "
            "yields paired with a Sahm rule still silent. Defensive tilt warranted."
        ),
    }
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _bad_sum_response() -> dict:
    """Probs summing to 0.5 -- fails the validator."""
    payload = {
        "regime_probs": {
            "RISK_ON": 0.10,
            "DEFLATION_SCARE": 0.10,
            "INFLATION_ACCEL": 0.10,
            "REAL_YIELD_SHOCK": 0.10,
            "RECESSION": 0.10,
        },
        "narrative": "Some narrative that is long enough to pass min_length.",
    }
    return {"choices": [{"message": {"content": json.dumps(payload)}}]}


def _garbage_response() -> dict:
    """Malformed JSON content -- triggers retry."""
    return {"choices": [{"message": {"content": "Sure! Here you go: not json"}}]}


def _markdown_fenced_response() -> dict:
    """Valid JSON wrapped in ```json fences -- the narrator must strip them."""
    payload = {
        "regime_probs": {
            "RISK_ON": 0.50,
            "DEFLATION_SCARE": 0.10,
            "INFLATION_ACCEL": 0.10,
            "REAL_YIELD_SHOCK": 0.10,
            "RECESSION": 0.20,
        },
        "narrative": "A fenced response echoing the 1995 soft-landing setup.",
    }
    body = "```json\n" + json.dumps(payload, indent=2) + "\n```"
    return {"choices": [{"message": {"content": body}}]}


def _make_asset_config(ticker: str = "BTC") -> AssetConfig:
    """Minimal AssetConfig for tests (frozen dataclass -- build directly)."""
    return AssetConfig(
        ticker=ticker,
        display_name=ticker,
        asset_class="crypto",
        calendar="247",
        trading_days_per_year=365.25,
        data_provider=type("Dummy", (), {}),
    )


def _make_snapshot() -> dict[str, float]:
    return {
        "real_yield_10y": 0.5,
        "nominal_10y": 1.5,
        "breakeven_10y": 2.0,
        "dxy": 110.0,
        "vix": 18.0,
        "fed_funds": 0.15,
        "ism_pmi": 50.0,
        "unemployment": 5.0,
        "cpi_yoy": 0.02,
        "sahm_recession": 0.0,
        "oil_term_structure": -1.0,
        "mortgage_30y": 3.5,
    }


def _make_trajectory(days: int = 10) -> pd.DataFrame:
    """A small daily DataFrame with a couple of numeric columns."""
    idx = pd.date_range("2024-01-01", periods=days, freq="D", name="date")
    return pd.DataFrame(
        {
            "real_yield_10y": [0.4 + 0.01 * i for i in range(days)],
            "vix": [18.0 - 0.1 * i for i in range(days)],
        },
        index=idx,
    )


def _mock_router() -> AsyncMock:
    """An AsyncMock standing in for a ModelRouter instance."""
    router = AsyncMock()
    router.generate = AsyncMock(return_value=_good_response())
    return router


# ---------------------------------------------------------------------------
# Test 1: Happy path
# ---------------------------------------------------------------------------


class TestHappyPath:
    """Mock returns valid JSON; output parsed; router called exactly once."""

    async def test_happy_path_parses_and_calls_router_once(
        self, tmp_path: Path
    ):
        router = _mock_router()
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        output = await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(),
            timestamp=datetime(2024, 3, 15, 12, 0, 0, tzinfo=timezone.utc),
        )

        # Output validated.
        assert isinstance(output, RegimeJudgeOutput)
        assert set(output.regime_probs.keys()) == set(Regime)
        assert 0.95 <= sum(output.regime_probs.values()) <= 1.05
        assert len(output.narrative) >= 20

        # Router called exactly once (no retry on happy path).
        assert router.generate.await_count == 1

    async def test_markdown_fences_are_stripped(self, tmp_path: Path):
        """LLM wraps JSON in ```json fences -- narrator strips them."""
        router = AsyncMock()
        router.generate = AsyncMock(return_value=_markdown_fenced_response())
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        output = await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(),
        )

        assert isinstance(output, RegimeJudgeOutput)
        assert router.generate.await_count == 1


# ---------------------------------------------------------------------------
# Test 2 / 10: Probabilities sum validator
# ---------------------------------------------------------------------------


class TestProbabilitiesValidator:
    """RegimeJudgeOutput rejects invalid probability distributions."""

    def test_accepts_exactly_one(self):
        out = RegimeJudgeOutput(
            regime_probs={
                Regime.RISK_ON: 1.0,
                Regime.DEFLATION_SCARE: 0.0,
                Regime.INFLATION_ACCEL: 0.0,
                Regime.REAL_YIELD_SHOCK: 0.0,
                Regime.RECESSION: 0.0,
            },
            narrative="All-in risk-on, echoing the 2013 taper tantrum setup.",
        )
        assert sum(out.regime_probs.values()) == pytest.approx(1.0)

    def test_accepts_within_tolerance(self):
        # Sum = 1.04 (within +/- 0.05).
        out = RegimeJudgeOutput(
            regime_probs={
                Regime.RISK_ON: 0.30,
                Regime.DEFLATION_SCARE: 0.20,
                Regime.INFLATION_ACCEL: 0.20,
                Regime.REAL_YIELD_SHOCK: 0.20,
                Regime.RECESSION: 0.14,
            },
            narrative="A balanced call within the 0.05 tolerance band of spec.",
        )
        assert 0.95 <= sum(out.regime_probs.values()) <= 1.05

    def test_rejects_sum_below_tolerance(self):
        with pytest.raises(ValidationError) as exc_info:
            RegimeJudgeOutput(
                regime_probs={
                    Regime.RISK_ON: 0.10,
                    Regime.DEFLATION_SCARE: 0.10,
                    Regime.INFLATION_ACCEL: 0.10,
                    Regime.REAL_YIELD_SHOCK: 0.10,
                    Regime.RECESSION: 0.10,
                },
                narrative="Sum is 0.5; this should fail validation outright.",
            )
        assert "sum" in str(exc_info.value).lower()

    def test_rejects_sum_above_tolerance(self):
        with pytest.raises(ValidationError):
            RegimeJudgeOutput(
                regime_probs={
                    Regime.RISK_ON: 0.50,
                    Regime.DEFLATION_SCARE: 0.30,
                    Regime.INFLATION_ACCEL: 0.30,
                    Regime.REAL_YIELD_SHOCK: 0.20,
                    Regime.RECESSION: 0.20,
                },
                narrative="Sum is 1.5; this should fail validation outright.",
            )

    def test_rejects_out_of_range_probability(self):
        with pytest.raises(ValidationError):
            RegimeJudgeOutput(
                regime_probs={
                    Regime.RISK_ON: 1.5,
                    Regime.DEFLATION_SCARE: 0.0,
                    Regime.INFLATION_ACCEL: 0.0,
                    Regime.REAL_YIELD_SHOCK: 0.0,
                    Regime.RECESSION: -0.5,  # negative -> out of range
                },
                narrative="Probability out of range; this must be rejected.",
            )

    def test_rejects_short_narrative(self):
        with pytest.raises(ValidationError):
            RegimeJudgeOutput(
                regime_probs={
                    Regime.RISK_ON: 1.0,
                    Regime.DEFLATION_SCARE: 0.0,
                    Regime.INFLATION_ACCEL: 0.0,
                    Regime.REAL_YIELD_SHOCK: 0.0,
                    Regime.RECESSION: 0.0,
                },
                narrative="too short",
            )


# ---------------------------------------------------------------------------
# Test 3: Malformed JSON triggers retry
# ---------------------------------------------------------------------------


class TestRetryLogic:
    """First call malformed -> retry with stricter prompt succeeds."""

    async def test_malformed_first_call_triggers_retry_then_success(
        self, tmp_path: Path
    ):
        router = AsyncMock()
        router.generate = AsyncMock(
            side_effect=[_garbage_response(), _good_response()]
        )
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        output = await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(),
        )

        assert isinstance(output, RegimeJudgeOutput)
        # Two calls: initial + retry.
        assert router.generate.await_count == 2


# ---------------------------------------------------------------------------
# Test 4: Cache hit skips the LLM
# ---------------------------------------------------------------------------


class TestCacheHit:
    """Pre-populated cache returns entry without calling the LLM."""

    async def test_cache_hit_skips_router_call(self, tmp_path: Path):
        router = _mock_router()
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        # Pre-populate cache by writing one row directly.
        out = RegimeJudgeOutput(
            regime_probs={
                Regime.RISK_ON: 0.50,
                Regime.DEFLATION_SCARE: 0.10,
                Regime.INFLATION_ACCEL: 0.10,
                Regime.REAL_YIELD_SHOCK: 0.10,
                Regime.RECESSION: 0.20,
            },
            narrative="Cached narrative echoing the 1995 soft-landing setup.",
        )
        as_of = date(2024, 3, 15)
        narrator._write_cache(
            cache_date=as_of,
            ticker="BTC",
            output=out,
            cached_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )

        # Now judge for the same (date, ticker): should hit cache.
        result = await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(ticker="BTC"),
            timestamp=datetime(2024, 3, 15, 12, 0, 0),
        )

        assert isinstance(result, RegimeJudgeOutput)
        assert result.narrative == out.narrative
        assert result.regime_probs == out.regime_probs
        # Router NOT called.
        assert router.generate.await_count == 0


# ---------------------------------------------------------------------------
# Test 5: Cache TTL expired -> refetch
# ---------------------------------------------------------------------------


class TestCacheTTLExpired:
    """Stale (>24h) cache entry triggers a refetch."""

    async def test_stale_cache_triggers_refetch(self, tmp_path: Path):
        router = _mock_router()
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        # Write a stale entry (cached 2 days ago).
        stale = RegimeJudgeOutput(
            regime_probs={
                Regime.RISK_ON: 0.50,
                Regime.DEFLATION_SCARE: 0.10,
                Regime.INFLATION_ACCEL: 0.10,
                Regime.REAL_YIELD_SHOCK: 0.10,
                Regime.RECESSION: 0.20,
            },
            narrative="Stale narrative from two days ago, long enough to pass.",
        )
        as_of = date(2024, 3, 15)
        narrator._write_cache(
            cache_date=as_of,
            ticker="BTC",
            output=stale,
            cached_at=datetime.now(timezone.utc).replace(tzinfo=None) - timedelta(days=2),
        )

        result = await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(ticker="BTC"),
            timestamp=datetime(2024, 3, 15, 12, 0, 0),
        )

        # Router WAS called (cache was stale).
        assert router.generate.await_count == 1
        # And we got a valid output back (from the mock).
        assert isinstance(result, RegimeJudgeOutput)
        # The new entry's narrative comes from the mock, NOT the stale one.
        assert result.narrative != stale.narrative


# ---------------------------------------------------------------------------
# Test 6: Async behaviour
# ---------------------------------------------------------------------------


class TestAsyncBehaviour:
    """``judge_and_narrate`` is a coroutine returning a coroutine object."""

    def test_judge_and_narrate_is_async_def(self):
        assert inspect.iscoroutinefunction(LLMJudgeNarrator.judge_and_narrate)

    async def test_judge_and_narrate_returns_awaitable(self, tmp_path: Path):
        router = _mock_router()
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        coro = narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(),
        )
        # It's a coroutine object (not yet a Task); awaiting it yields the result.
        assert asyncio.iscoroutine(coro)
        try:
            result = await coro
            assert isinstance(result, RegimeJudgeOutput)
        except BaseException:
            # If the await raised, close the coro to avoid "never awaited" warning.
            coro.close()
            raise


# ---------------------------------------------------------------------------
# Test 7: Fed statements stub (empty string graceful)
# ---------------------------------------------------------------------------


class TestFedStatementsStub:
    """Empty ``fed_statements`` works without breaking the prompt."""

    async def test_empty_fed_statements_works(self, tmp_path: Path):
        router = _mock_router()
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        output = await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(),
            fed_statements="",
        )

        assert isinstance(output, RegimeJudgeOutput)
        # Inspect the actual prompt sent to the LLM.
        sent_messages = router.generate.await_args.kwargs.get("messages") or \
            router.generate.await_args.args[0]
        sent_prompt = sent_messages[0]["content"]
        # The placeholder text must be present.
        assert "(no recent statements available)" in sent_prompt

    async def test_non_empty_fed_statements_flow_into_prompt(
        self, tmp_path: Path
    ):
        router = _mock_router()
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        await narrator.judge_and_narrate(
            factor_snapshot=_make_snapshot(),
            trajectory=_make_trajectory(),
            asset_config=_make_asset_config(),
            fed_statements="FOMC Jan 2024: rates unchanged, patient stance.",
        )

        sent_messages = router.generate.await_args.kwargs.get("messages") or \
            router.generate.await_args.args[0]
        sent_prompt = sent_messages[0]["content"]
        assert "FOMC Jan 2024" in sent_prompt


# ---------------------------------------------------------------------------
# Test 8: Both attempts fail -> LLMJudgeError
# ---------------------------------------------------------------------------


class TestDoubleFailureRaises:
    """Two malformed responses -> LLMJudgeError; caller falls back."""

    async def test_two_failures_raise_llm_judge_error(self, tmp_path: Path):
        router = AsyncMock()
        router.generate = AsyncMock(
            side_effect=[_garbage_response(), _garbage_response()]
        )
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        with pytest.raises(LLMJudgeError):
            await narrator.judge_and_narrate(
                factor_snapshot=_make_snapshot(),
                trajectory=_make_trajectory(),
                asset_config=_make_asset_config(),
            )

        # Two attempts made before giving up.
        assert router.generate.await_count == 2

    async def test_bad_sum_then_garbage_raises(self, tmp_path: Path):
        """First call sums wrong (ValidationError), second is garbage."""
        router = AsyncMock()
        router.generate = AsyncMock(
            side_effect=[_bad_sum_response(), _garbage_response()]
        )
        narrator = LLMJudgeNarrator(model_router=router, cache_dir=tmp_path)

        with pytest.raises(LLMJudgeError):
            await narrator.judge_and_narrate(
                factor_snapshot=_make_snapshot(),
                trajectory=_make_trajectory(),
                asset_config=_make_asset_config(),
            )
        assert router.generate.await_count == 2

    async def test_no_router_raises_immediately(self, tmp_path: Path):
        """Constructing without a router is fine; CALLING without one errors."""
        narrator = LLMJudgeNarrator(model_router=None, cache_dir=tmp_path)
        with pytest.raises(LLMJudgeError):
            await narrator.judge_and_narrate(
                factor_snapshot=_make_snapshot(),
                trajectory=_make_trajectory(),
                asset_config=_make_asset_config(),
            )


# ---------------------------------------------------------------------------
# Test 9: Trajectory summary handles edge cases
# ---------------------------------------------------------------------------


class TestTrajectorySummary:
    """The trajectory summary degrades gracefully on bad input."""

    def test_none_trajectory(self):
        s = LLMJudgeNarrator._summarise_trajectory(None)
        assert "no trajectory" in s.lower()

    def test_empty_dataframe(self):
        s = LLMJudgeNarrator._summarise_trajectory(pd.DataFrame())
        assert "empty" in s.lower()

    def test_numeric_trajectory_shows_delta(self):
        traj = pd.DataFrame(
            {"vix": [20.0, 18.0]},
            index=pd.date_range("2024-01-01", periods=2, freq="D"),
        )
        s = LLMJudgeNarrator._summarise_trajectory(traj)
        assert "vix" in s
        assert "20.0" in s
        assert "18.0" in s
        assert "delta=-2.000" in s

    def test_nan_values_handled(self):
        traj = pd.DataFrame(
            {"vix": [float("nan"), 18.0]},
            index=pd.date_range("2024-01-01", periods=2, freq="D"),
        )
        s = LLMJudgeNarrator._summarise_trajectory(traj)
        # No crash; summary still mentions the column.
        assert "vix" in s
