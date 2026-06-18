"""Tests for ``src/research/macro/model.py`` (MacroRegimeModel, W3/T14).

Covers the 10 required scenarios from the W3/T14 spec.  All tests use
synthetic factor frames + mocked :class:`LLMJudgeNarrator` so no network
call is ever made.

Scenarios
---------

1. ``alpha=1.0, use_llm=False`` -> rules-only, source="rules", narrative=None.
2. ``alpha=1.0, use_llm=True``  -> STILL rules-only (LLM skipped because
   ``alpha >= 1.0``); judge.judge_and_narrate is never called.
3. ``alpha=0.7, use_llm=False`` -> :class:`ValueError` (Metis G7 guardrail:
   "alpha < 1.0 requires use_llm=True -- ambiguous config rejected").
4. ``alpha=0.7, use_llm=True`` but ``judge=None`` at construction ->
   :class:`ValueError` (use_llm requires a judge).
5. ``alpha=0.7, use_llm=True, judge=<mock>`` -> ensemble blend; the final
   probability for each regime equals ``alpha * rules_p + (1-alpha) * llm_p``.
6. Determinism: same ``factor_df`` + ``alpha=1.0`` + ``use_llm=False`` called
   twice produces byte-identical :class:`RegimeClassification`.
7. LLM failure fallback: mock raises ``LLMJudgeError`` -> the ensembler
   catches it and returns ``source="rules"``, ``narrative=None``.
8. :class:`RegimeClassification` is frozen -- attribute assignment raises.
9. Timestamp slicing: passing ``timestamp`` returns the probs row at-or-before
   that timestamp (NOT the last row).
10. Argmax: ``regime`` field is the ``Regime`` with the highest probability.
"""

from __future__ import annotations

import dataclasses
from datetime import datetime, timezone
from unittest.mock import AsyncMock

import numpy as np
import pandas as pd
import pytest

from src.research.data import AssetConfig
from src.research.macro.model import MacroRegimeModel, RegimeClassification
from src.research.macro.narrator import LLMJudgeError, RegimeJudgeOutput
from src.research.macro.regimes import REGIME_COLUMNS, Regime, RulesBasedClassifier


# ---------------------------------------------------------------------------
# Synthetic factor frame (mirrors test_research_macro_regimes.py pattern)
# ---------------------------------------------------------------------------
#
# A daily-indexed frame of the 12 canonical factors over ~10 years so the
# 5-year rolling z-score window has enough history.  Default levels produce
# "neutral" macro conditions (no regime strongly triggers).

_DEFAULT_LEVELS: dict[str, float] = {
    "real_yield_10y": 0.5,
    "nominal_10y": 2.0,
    "breakeven_10y": 2.0,
    "dxy": 95.0,
    "vix": 16.0,
    "fed_funds": 1.0,
    "ism_pmi": 52.0,
    "unemployment": 4.0,
    "cpi_yoy": 0.02,
    "oil_term_structure": -2.0,
    "mortgage_30y": 3.5,
}

_DEFAULT_NOISE: dict[str, float] = {
    "real_yield_10y": 0.05,
    "nominal_10y": 0.05,
    "breakeven_10y": 0.05,
    "dxy": 0.5,
    "vix": 0.5,
    "fed_funds": 0.05,
    "ism_pmi": 0.5,
    "unemployment": 0.05,
    "cpi_yoy": 0.002,
    "oil_term_structure": 0.2,
    "mortgage_30y": 0.05,
}


def _synthetic_factor_df(
    days: int = 3800,
    start_date: str = "2010-01-01",
    overrides: dict[str, float | pd.Series] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a daily ``factor_df`` with all 12 canonical columns."""
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start_date, periods=days, freq="D", name="date")

    cols: dict[str, np.ndarray] = {}
    for col, level in _DEFAULT_LEVELS.items():
        noise = _DEFAULT_NOISE.get(col, 0.0)
        cols[col] = level + rng.normal(0.0, noise, size=days)
    cols["sahm_recession"] = np.zeros(days, dtype=bool)

    df = pd.DataFrame(cols, index=idx)

    if overrides:
        for col, val in overrides.items():
            if isinstance(val, pd.Series):
                df[col] = val.reindex(df.index, method="ffill")
            else:
                df[col] = val

    return df


# ---------------------------------------------------------------------------
# Other helpers
# ---------------------------------------------------------------------------


def _make_asset_config(ticker: str = "BTC-USD") -> AssetConfig:
    """Minimal AssetConfig for tests (frozen dataclass -- build directly)."""
    return AssetConfig(
        ticker=ticker,
        display_name=ticker,
        asset_class="crypto",
        calendar="247",
        trading_days_per_year=365.25,
        data_provider=type("Dummy", (), {}),
    )


def _mock_judge(
    probs: dict[Regime, float] | None = None,
    narrative: str | None = None,
) -> AsyncMock:
    """An AsyncMock standing in for an :class:`LLMJudgeNarrator` instance.

    ``judge_and_narrate`` is mocked to return a canned
    :class:`RegimeJudgeOutput`.  Tests can inspect ``await_count`` to
    verify the judge was/wasn't called.
    """
    canned_probs = probs or {
        Regime.RISK_ON: 0.40,
        Regime.DEFLATION_SCARE: 0.15,
        Regime.INFLATION_ACCEL: 0.15,
        Regime.REAL_YIELD_SHOCK: 0.10,
        Regime.RECESSION: 0.20,
    }
    canned_narrative = narrative or (
        "Echoes of the Q4 2018 selloff: real yields rose while the Sahm "
        "rule stayed silent; a defensive tilt is warranted here."
    )
    output = RegimeJudgeOutput(regime_probs=canned_probs, narrative=canned_narrative)
    judge = AsyncMock()
    judge.judge_and_narrate = AsyncMock(return_value=output)
    return judge


def _failing_judge(exc: Exception | None = None) -> AsyncMock:
    """A mock judge whose ``judge_and_narrate`` always raises."""
    judge = AsyncMock()
    judge.judge_and_narrate = AsyncMock(side_effect=exc or LLMJudgeError("boom"))
    return judge


# ---------------------------------------------------------------------------
# Shared fixture: a default classifier + factor frame
# ---------------------------------------------------------------------------


@pytest.fixture
def rules_classifier() -> RulesBasedClassifier:
    return RulesBasedClassifier()


@pytest.fixture
def factor_df() -> pd.DataFrame:
    return _synthetic_factor_df()


# ===========================================================================
# Test 1: alpha=1.0, use_llm=False -> rules-only
# ===========================================================================


class TestRulesOnlyDefault:
    """Default path: ``alpha=1.0, use_llm=False`` returns rules-only output."""

    async def test_rules_only_returns_correct_source_and_narrative(
        self, rules_classifier, factor_df
    ):
        model = MacroRegimeModel(rules=rules_classifier, judge=None)
        result = await model.classify(factor_df)

        assert isinstance(result, RegimeClassification)
        assert result.source == "rules"
        assert result.narrative is None
        assert result.alpha == 1.0

    async def test_rules_only_probs_are_regime_keyed_and_sum_to_one(
        self, rules_classifier, factor_df
    ):
        model = MacroRegimeModel(rules=rules_classifier)
        result = await model.classify(factor_df)

        # Probs dict is keyed by Regime enum members, not strings.
        assert set(result.probs.keys()) == set(Regime)
        assert all(isinstance(k, Regime) for k in result.probs)
        assert sum(result.probs.values()) == pytest.approx(1.0, abs=1e-9)

    async def test_rules_only_regime_is_valid_enum_member(
        self, rules_classifier, factor_df
    ):
        model = MacroRegimeModel(rules=rules_classifier)
        result = await model.classify(factor_df)

        assert isinstance(result.regime, Regime)
        # And it matches argmax of probs.
        assert result.regime == max(result.probs, key=result.probs.get)


# ===========================================================================
# Test 2: alpha=1.0, use_llm=True -> STILL rules-only (LLM skipped)
# ===========================================================================


class TestAlphaOneSkipsLLM:
    """``alpha=1.0`` means "rules-only" -- even with ``use_llm=True`` the
    judge is never called (no blend to perform)."""

    async def test_alpha_one_with_use_llm_does_not_call_judge(
        self, rules_classifier, factor_df
    ):
        judge = _mock_judge()
        model = MacroRegimeModel(rules=rules_classifier, judge=judge)

        result = await model.classify(factor_df, alpha=1.0, use_llm=True)

        # Judge was NOT called (alpha >= 1.0 short-circuits the LLM path).
        assert judge.judge_and_narrate.await_count == 0
        assert result.source == "rules"
        assert result.narrative is None


# ===========================================================================
# Test 3: alpha=0.7, use_llm=False -> ValueError (Metis G7 guardrail)
# ===========================================================================


class TestGuardrailAlphaWithoutLLM:
    """``alpha < 1.0`` + ``use_llm=False`` is ambiguous; rejected."""

    async def test_alpha_below_one_without_llm_raises(self, rules_classifier, factor_df):
        model = MacroRegimeModel(rules=rules_classifier, judge=_mock_judge())
        with pytest.raises(ValueError, match="alpha.*use_llm"):
            await model.classify(factor_df, alpha=0.7, use_llm=False)

    async def test_guardrail_message_mentions_both_knobs(
        self, rules_classifier, factor_df
    ):
        model = MacroRegimeModel(rules=rules_classifier)
        with pytest.raises(ValueError) as exc_info:
            await model.classify(factor_df, alpha=0.5, use_llm=False)
        msg = str(exc_info.value).lower()
        # The message should guide the operator to EITHER knob.
        assert "alpha" in msg
        assert "use_llm" in msg


# ===========================================================================
# Test 4: alpha=0.7, use_llm=True, judge=None -> ValueError
# ===========================================================================


class TestGuardrailLLMWithoutJudge:
    """``use_llm=True`` requires a judge to have been passed at construction."""

    async def test_use_llm_without_judge_raises(self, rules_classifier, factor_df):
        model = MacroRegimeModel(rules=rules_classifier, judge=None)
        with pytest.raises(ValueError, match="judge"):
            await model.classify(factor_df, alpha=0.7, use_llm=True)


# ===========================================================================
# Test 5: alpha=0.7, use_llm=True, judge=<mock> -> ensemble blend
# ===========================================================================


class TestEnsembleBlend:
    """Weighted ensemble: ``final = alpha * rules + (1-alpha) * llm``."""

    async def test_ensemble_calls_judge_and_blends(
        self, rules_classifier, factor_df
    ):
        judge = _mock_judge()
        model = MacroRegimeModel(rules=rules_classifier, judge=judge)

        alpha = 0.7
        result = await model.classify(
            factor_df,
            alpha=alpha,
            use_llm=True,
            asset_config=_make_asset_config(),
        )

        # Judge WAS called exactly once.
        assert judge.judge_and_narrate.await_count == 1
        assert result.source == "ensemble"
        assert isinstance(result.narrative, str)
        assert len(result.narrative) >= 20

    async def test_ensemble_blend_matches_formula(self, rules_classifier, factor_df):
        """For each regime, final = alpha*rules + (1-alpha)*llm (within tol)."""
        # Get the rules-only baseline at the last timestamp.
        rules_probs_df = rules_classifier.classify(factor_df)
        rules_last = rules_probs_df.iloc[-1].to_dict()  # string keys

        # Canned LLM probs (Regime keys).
        llm_probs = {
            Regime.RISK_ON: 0.40,
            Regime.DEFLATION_SCARE: 0.15,
            Regime.INFLATION_ACCEL: 0.15,
            Regime.REAL_YIELD_SHOCK: 0.10,
            Regime.RECESSION: 0.20,
        }
        judge = _mock_judge(probs=llm_probs)
        model = MacroRegimeModel(rules=rules_classifier, judge=judge)

        alpha = 0.6
        result = await model.classify(
            factor_df,
            alpha=alpha,
            use_llm=True,
            asset_config=_make_asset_config(),
        )

        # Verify the blend formula per regime.
        for r in Regime:
            expected = alpha * rules_last[r.value] + (1.0 - alpha) * llm_probs[r]
            assert result.probs[r] == pytest.approx(expected, abs=1e-9), (
                f"blend mismatch for {r.name}: expected {expected}, got {result.probs[r]}"
            )

        # And probs still sum to ~1.
        assert sum(result.probs.values()) == pytest.approx(1.0, abs=0.05)


# ===========================================================================
# Test 6: Determinism
# ===========================================================================


class TestDeterminism:
    """Same input + rules-only mode -> byte-identical output across calls."""

    async def test_rules_only_is_deterministic(self, rules_classifier, factor_df):
        model = MacroRegimeModel(rules=rules_classifier)
        r1 = await model.classify(factor_df, alpha=1.0, use_llm=False)
        r2 = await model.classify(factor_df, alpha=1.0, use_llm=False)

        # Frozen dataclass -> equality is by value.
        assert r1 == r2
        # Probs dicts match exactly.
        assert r1.probs == r2.probs
        assert r1.regime == r2.regime


# ===========================================================================
# Test 7: LLM failure falls back to rules-only
# ===========================================================================


class TestLLMFailureFallback:
    """If the judge raises, the ensembler catches + falls back to rules."""

    async def test_llm_failure_returns_rules_source(
        self, rules_classifier, factor_df
    ):
        judge = _failing_judge(LLMJudgeError("simulated double failure"))
        model = MacroRegimeModel(rules=rules_classifier, judge=judge)

        result = await model.classify(
            factor_df,
            alpha=0.5,
            use_llm=True,
            asset_config=_make_asset_config(),
        )

        # Judge WAS attempted.
        assert judge.judge_and_narrate.await_count == 1
        # But we fell back to rules-only.
        assert result.source == "rules"
        assert result.narrative is None
        # Alpha is still reported as the requested value (caller sees what
        # they asked for; source tells them what actually ran).
        assert result.alpha == 0.5

    async def test_llm_generic_exception_also_falls_back(
        self, rules_classifier, factor_df
    ):
        """Any exception (not just LLMJudgeError) triggers the fallback."""
        judge = _failing_judge(RuntimeError("network glitch"))
        model = MacroRegimeModel(rules=rules_classifier, judge=judge)

        result = await model.classify(
            factor_df,
            alpha=0.5,
            use_llm=True,
            asset_config=_make_asset_config(),
        )
        assert result.source == "rules"
        assert result.narrative is None


# ===========================================================================
# Test 8: RegimeClassification is frozen
# ===========================================================================


class TestFrozenDataclass:
    """``RegimeClassification`` is immutable -- assignment raises."""

    def test_cannot_mutate_regime(self):
        rc = RegimeClassification(
            regime=Regime.RISK_ON,
            probs={r: 0.2 for r in Regime},
            alpha=1.0,
            narrative=None,
            source="rules",
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            rc.regime = Regime.RECESSION  # type: ignore[misc]

    def test_cannot_mutate_alpha(self):
        rc = RegimeClassification(
            regime=Regime.RISK_ON,
            probs={r: 0.2 for r in Regime},
            alpha=1.0,
            narrative=None,
            source="rules",
        )
        with pytest.raises((AttributeError, dataclasses.FrozenInstanceError)):
            rc.alpha = 0.5  # type: ignore[misc]

    def test_is_frozen_dataclass(self):
        # The dataclass decorator was applied with frozen=True.
        assert dataclasses.is_dataclass(RegimeClassification)
        # Frozen-instance fields have no setter.
        fields = {f.name: f for f in dataclasses.fields(RegimeClassification)}
        assert "regime" in fields
        assert "probs" in fields
        assert "alpha" in fields
        assert "narrative" in fields
        assert "source" in fields
        # timestamp defaults to None.
        assert fields["timestamp"].default is None


# ===========================================================================
# Test 9: Timestamp slicing
# ===========================================================================


class TestTimestampSlicing:
    """Passing ``timestamp`` returns the row at-or-before that timestamp."""

    async def test_timestamp_returns_correct_row(self, rules_classifier, factor_df):
        model = MacroRegimeModel(rules=rules_classifier)

        # Pick a timestamp in the MIDDLE of the frame (not the last row).
        mid_idx = factor_df.index[len(factor_df.index) // 2]
        ts = mid_idx.to_pydatetime()

        result = await model.classify(factor_df, timestamp=ts)

        # Compute expected rules probs at that timestamp directly.
        expected_df = rules_classifier.classify(factor_df)
        expected_row = expected_df.loc[mid_idx]

        for r in Regime:
            assert result.probs[r] == pytest.approx(
                float(expected_row[r.value]), abs=1e-9
            ), f"mismatch at {r.name} for ts={ts}"

        # And the result's timestamp is echoed back.
        assert result.timestamp == ts

    async def test_timestamp_before_start_raises(self, rules_classifier, factor_df):
        model = MacroRegimeModel(rules=rules_classifier)
        # A timestamp before the frame starts.
        early = factor_df.index[0] - pd.Timedelta(days=10)
        with pytest.raises(ValueError, match="timestamp"):
            await model.classify(factor_df, timestamp=early.to_pydatetime())


# ===========================================================================
# Test 10: Argmax picks the dominant regime
# ===========================================================================


class TestArgmaxRegime:
    """``regime`` field is the :class:`Regime` with the highest probability."""

    async def test_argmax_matches_max_prob_regime(self, rules_classifier, factor_df):
        """Force RECESSION dominant via a Sahm flag and verify argmax."""
        # Override sahm_recession=True to push RECESSION prob to 1.0.
        forced_df = _synthetic_factor_df(
            overrides={"sahm_recession": True},
        )
        model = MacroRegimeModel(rules=rules_classifier)
        result = await model.classify(forced_df)

        # The dominant regime should be RECESSION (Sahm forces logit=1.0).
        assert result.regime == Regime.RECESSION
        # And it matches argmax of the returned probs.
        argmax = max(result.probs, key=result.probs.get)
        assert argmax == Regime.RECESSION
        assert argmax == result.regime

    async def test_argmax_on_neutral_window_is_risk_on(
        self, rules_classifier, factor_df
    ):
        """In a known-neutral window (2017), RISK_ON dominates (residual regime).

        We slice to a timestamp in the 2017-2018 window that T12's
        ``test_risk_on_is_top_in_neutral_window`` already proved is
        RISK_ON-dominant on average.  Picking the last day of the whole
        frame is fragile (any single day can flip), so we anchor to
        a neutral-window timestamp instead.
        """
        model = MacroRegimeModel(rules=rules_classifier)

        # Mid-2017: well past the 5y z-score warmup, factors near their
        # trailing means -> stress-regime sigmoids soft -> RISK_ON wins.
        ts = pd.Timestamp("2017-06-15").to_pydatetime()
        result = await model.classify(factor_df, timestamp=ts)

        assert result.regime == Regime.RISK_ON
        assert result.probs[result.regime] == max(result.probs.values())


# ===========================================================================
# Bonus: async contract + source field enumeration
# ===========================================================================


class TestAsyncContract:
    """``classify`` is an ``async def`` coroutine (LLM path is async)."""

    def test_classify_is_coroutine_function(self):
        import inspect

        assert inspect.iscoroutinefunction(MacroRegimeModel.classify)
