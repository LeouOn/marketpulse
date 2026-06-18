"""Tests for ``src.research/macro/regimes.py`` (RulesBasedClassifier, T12).

Covers the 7 required mocked unit-test scenarios + the 6-episode live
backrun validation (PRIMARY acceptance criterion) + the regime-tape
generation test.

Layout
------

* Tests 1-7 (mocked, no network):
    1. ``_sigmoid`` math correctness.
    2. ``classify()`` returns a 5-column DataFrame with canonical names.
    3. Softmax normalization -- probabilities sum to 1.0 per row.
    4. Missing factor (VIX column absent) -> DEFLATION_SCARE logit = 0
       (regime suppressed; softmax renormalises the rest).
    5. RECESSION takes precedence when ``sahm_recession=True``.
    6. RISK_ON is dominant when no other regime triggers (factors neutral).
    7. Determinism -- same input twice produces byte-identical output.

* Tests 8-13 (``@pytest.mark.live``, skipped unless ``RUN_LIVE_TESTS=1``):
    The 6-episode historical backrun.  Each episode's expected regime
    must appear in the top-2 mean probabilities across the window.
    Requires a real ``FRED_API_KEY`` (the MacroFactorProvider fetches
    live FRED/Yahoo data on first run; subsequent runs hit
    ``data/macro/factors.parquet``).

* Test 14 (live): generates the regime tape CSV artefact at
  ``.omo/evidence/task-12-regime-tape.csv`` and asserts that all 5
  regimes appear at least once + RISK_ON is the most common.
"""

from __future__ import annotations

import os
import shutil
from datetime import date
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

# Module under test.  Importing at module scope produces the expected
# ModuleNotFoundError during the RED phase (before regimes.py exists).
from src.research.macro.regimes import (  # noqa: E402
    REGIME_COLUMNS,
    Regime,
    RulesBasedClassifier,
    _sigmoid,
    generate_regime_tape,
)


# ---------------------------------------------------------------------------
# Live-test opt-in (mirrors T11's pattern in test_research_macro_factors.py)
# ---------------------------------------------------------------------------

_LIVE_ENABLED = os.getenv("RUN_LIVE_TESTS", "") == "1"
_SKIP_LIVE = pytest.mark.skipif(
    not _LIVE_ENABLED,
    reason=(
        "Set RUN_LIVE_TESTS=1 to run live FRED/Yahoo backrun validation "
        "(requires FRED_API_KEY)."
    ),
)


# ---------------------------------------------------------------------------
# Synthetic factor frame builder
# ---------------------------------------------------------------------------
#
# Builds a daily-indexed frame of the 12 canonical factors over a
# ``days`` day span starting ``start_date``.  ``overrides`` lets each
# test inject per-column constants or Series (e.g. a VIX spike over a
# sub-window).  Defaults produce "neutral" macro conditions: typical
# post-2010 levels + small Gaussian noise so rolling z-scores have
# well-defined std without trivially triggering any regime.

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
    drop_cols: list[str] | None = None,
    seed: int = 42,
) -> pd.DataFrame:
    """Build a daily ``factor_df`` with all 12 canonical columns.

    Args:
        days: number of daily rows.  Default 3800 (~10.4 years)
            clears the 5-year z-score warmup window AND leaves a
            multi-year post-warmup span (2015+) for the regime-
            neutral assertions to slice into.
        start_date: ISO date string for the first row.
        overrides: optional dict mapping column name to either a scalar
            (broadcast to all rows) or a ``pd.Series`` indexed however
            (will be reindexed onto the frame's index via ``set_value``
            semantics -- caller should pre-align if it cares).
        drop_cols: columns to omit entirely (for Metis EC1 tests).
        seed: RNG seed for reproducibility.

    Returns:
        Daily-indexed DataFrame with all 12 factor columns (minus any
        in ``drop_cols``).  ``sahm_recession`` is always present as a
        bool column (False by default; overrideable via ``overrides``).
    """
    rng = np.random.default_rng(seed)
    idx = pd.date_range(start_date, periods=days, freq="D", name="date")
    drop = set(drop_cols or [])

    cols: dict[str, np.ndarray | list[bool]] = {}
    for col, level in _DEFAULT_LEVELS.items():
        if col in drop:
            continue
        noise = _DEFAULT_NOISE.get(col, 0.0)
        cols[col] = level + rng.normal(0.0, noise, size=days)

    # sahm_recession is bool, default False; allow override.
    if "sahm_recession" not in drop:
        cols["sahm_recession"] = [False] * days

    df = pd.DataFrame(cols, index=idx)

    if overrides:
        for col, val in overrides.items():
            if col in drop:
                continue
            if isinstance(val, pd.Series):
                # Reindex onto df's index (ffill gaps, leave NaN where
                # the override Series has nothing).
                df[col] = val.reindex(df.index, method="ffill")
            else:
                df[col] = val

    return df


# ===========================================================================
# Test 1: _sigmoid correctness
# ===========================================================================


class TestSigmoid:
    """``_sigmoid(x, threshold, slope) = 1 / (1 + exp(-slope*(x-t)))``."""

    def test_at_threshold_returns_half(self):
        # At x == threshold, sigmoid is exactly 0.5 regardless of slope.
        assert _sigmoid(1.0, 1.0, 2.0) == pytest.approx(0.5)
        assert _sigmoid(0.0, 0.0, 1.0) == pytest.approx(0.5)
        assert _sigmoid(-1.5, -1.5, 1.5) == pytest.approx(0.5)

    def test_above_threshold_approaches_one(self):
        # For x >> threshold + a few/slope, sigmoid -> 1 (asymptotic).
        # σ(10, 0, 1) = 1/(1+exp(-10)) ≈ 0.99995 -> within 1e-4 of 1.
        # σ(5, 1, 2) = 1/(1+exp(-8)) ≈ 0.99966 -> within 5e-4 of 1.
        assert _sigmoid(10.0, 0.0, 1.0) == pytest.approx(1.0, abs=1e-4)
        assert _sigmoid(5.0, 1.0, 2.0) == pytest.approx(1.0, abs=5e-4)

    def test_below_threshold_approaches_zero(self):
        # For x << threshold, sigmoid -> 0 (asymptotic).
        assert _sigmoid(-10.0, 0.0, 1.0) == pytest.approx(0.0, abs=1e-4)
        assert _sigmoid(-5.0, 1.0, 2.0) == pytest.approx(0.0, abs=5e-4)

    def test_known_value(self):
        # x=2, t=1, s=2: 1/(1+exp(-2)) = 1/(1+0.1353) = 0.8808
        assert _sigmoid(2.0, 1.0, 2.0) == pytest.approx(0.8808, abs=1e-4)

    def test_nan_propagates(self):
        # Missing factor -> NaN input -> NaN output (Metis EC1 relies on this).
        assert np.isnan(_sigmoid(float("nan"), 0.0, 1.0))

    def test_series_input_preserves_index(self):
        # Series in -> Series out with the same index.
        s = pd.Series([0.0, 1.0, 2.0], index=pd.date_range("2020-01-01", periods=3))
        out = _sigmoid(s, threshold=1.0, slope=2.0)
        assert isinstance(out, pd.Series)
        assert out.index.equals(s.index)
        assert out.iloc[0] == pytest.approx(0.119, abs=1e-3)  # x=0, t=1
        assert out.iloc[1] == pytest.approx(0.5)               # x=t
        assert out.iloc[2] == pytest.approx(0.881, abs=1e-3)  # x=2, t=1


# ===========================================================================
# Test 2: classify() shape + columns
# ===========================================================================


class TestClassifyShape:
    """``classify()`` returns a 5-column DataFrame with canonical names."""

    def test_returns_dataframe(self):
        df = _synthetic_factor_df()
        out = RulesBasedClassifier().classify(df)
        assert isinstance(out, pd.DataFrame)

    def test_columns_match_regime_enum(self):
        df = _synthetic_factor_df()
        out = RulesBasedClassifier().classify(df)
        assert list(out.columns) == list(REGIME_COLUMNS)
        assert list(out.columns) == [r.value for r in Regime]

    def test_index_preserved(self):
        df = _synthetic_factor_df(days=500)
        out = RulesBasedClassifier().classify(df)
        assert out.index.equals(df.index)

    def test_all_values_in_unit_interval(self):
        # Probabilities must be in [0, 1].
        df = _synthetic_factor_df()
        out = RulesBasedClassifier().classify(df)
        assert (out.to_numpy() >= 0.0).all()
        assert (out.to_numpy() <= 1.0).all()


# ===========================================================================
# Test 3: Softmax normalization -- rows sum to 1
# ===========================================================================


class TestSoftmaxNormalization:
    """Each row of the output sums to 1.0 (within float tolerance)."""

    def test_rows_sum_to_one(self):
        df = _synthetic_factor_df()
        out = RulesBasedClassifier().classify(df)
        row_sums = out.sum(axis=1)
        # Drop the warmup window where z-scores may be NaN-driven.
        # We still expect rows to sum to 1 there too (uniform softmax).
        np.testing.assert_allclose(
            row_sums.to_numpy(),
            np.ones(len(row_sums)),
            atol=1e-12,
            err_msg="Every row must sum to 1.0 after softmax",
        )

    def test_warmup_rows_also_sum_to_one(self):
        # Belt-and-suspenders: even on rows with all-NaN z-scores
        # (warmup / constant columns), softmax of [NaN->0]*5 gives
        # uniform 1/5 = 0.2 each, summing to 1.0.
        df = _synthetic_factor_df(days=10)  # well under 2-day min_periods warmup
        out = RulesBasedClassifier().classify(df)
        row_sums = out.sum(axis=1).to_numpy()
        np.testing.assert_allclose(row_sums, np.ones(10), atol=1e-12)


# ===========================================================================
# Test 4: Missing-factor handling (Metis EC1)
# ===========================================================================


class TestMissingFactor:
    """Missing factor column -> dependent regime's logit is 0.

    When VIX is absent, the DEFLATION_SCARE logit becomes 0 because
    ``sigmoid(NaN) -> NaN -> .fillna(0)`` makes the VIX factor of the
    product equal to 0.  Softmax then renormalises the surviving
    regimes.

    The test compares two scenarios with identical factors EXCEPT
    that one has VIX absent: the VIX-present scenario produces a
    higher DEFLATION_SCARE probability under a vol-spike pattern,
    while the VIX-absent scenario suppresses DEFLATION_SCARE.
    """

    def test_logits_deflation_scare_is_zero_when_vix_missing(self):
        # Direct test on compute_logits: the logit value is the
        # pre-softmax probability; with VIX absent it must be 0.
        df_no_vix = _synthetic_factor_df(drop_cols=["vix"])
        logits = RulesBasedClassifier().compute_logits(df_no_vix)
        # Every DEFLATION_SCARE logit must be exactly 0.0 (sigmoid(NaN)
        # -> NaN -> fillna(0) -> product with anything = 0).
        assert (logits["DEFLATION_SCARE"] == 0.0).all()

    def test_logits_deflation_scare_is_zero_when_breakeven_missing(self):
        # Breakevens feed BOTH DEFLATION_SCARE and INFLATION_ACCEL and
        # REAL_YIELD_SHOCK -- all three must collapse to 0.
        df_no_bev = _synthetic_factor_df(drop_cols=["breakeven_10y"])
        logits = RulesBasedClassifier().compute_logits(df_no_bev)
        assert (logits["DEFLATION_SCARE"] == 0.0).all()
        assert (logits["INFLATION_ACCEL"] == 0.0).all()
        assert (logits["REAL_YIELD_SHOCK"] == 0.0).all()

    def test_vix_spike_ignored_when_vix_column_absent(self):
        # Build a realistic DEFLATION_SCARE pattern: vol spike AND
        # breakevens collapse.  Inject both into the VIX-present frame;
        # the VIX-absent frame only gets the breakeven collapse (since
        # VIX column is dropped).  The presence of VIX must materially
        # raise DEFLATION_SCARE probability relative to its absence.
        days = 2500
        idx = pd.date_range("2010-01-01", periods=days, freq="D")
        spike_at = 2000  # day index where the spike starts

        # Shared breakeven-collapse pattern.
        bev_values = np.full(days, 2.0)
        bev_values[spike_at:spike_at + 60] = 0.5  # breakeven collapse
        bev_series = pd.Series(bev_values, index=idx)

        # VIX spike pattern.
        vix_values = np.full(days, 16.0)
        vix_values[spike_at:spike_at + 60] = 80.0  # 2-month vol spike
        vix_series = pd.Series(vix_values, index=idx)

        # VIX-present: both signals.
        df_with_vix = _synthetic_factor_df()
        df_with_vix["vix"] = vix_series
        df_with_vix["breakeven_10y"] = bev_series

        # VIX-absent: only the breakeven-collapse leg reaches the
        # classifier (the VIX column is dropped entirely).
        df_no_vix = _synthetic_factor_df(drop_cols=["vix"])
        df_no_vix["breakeven_10y"] = bev_series

        clf = RulesBasedClassifier()
        probs_with = clf.classify(df_with_vix)
        probs_without = clf.classify(df_no_vix)

        # In the VIX-present case, DEFLATION_SCARE probability during
        # the spike window must be substantially higher than in the
        # VIX-absent case (where the VIX factor of the product is
        # forced to 0 by Metis EC1).
        spike_window = slice(idx[spike_at + 30], idx[spike_at + 59])
        with_vix_mean = probs_with.loc[spike_window, "DEFLATION_SCARE"].mean()
        without_mean = probs_without.loc[spike_window, "DEFLATION_SCARE"].mean()

        assert with_vix_mean > without_mean + 0.05, (
            f"DEFLATION_SCARE with VIX present ({with_vix_mean:.3f}) should be "
            f">= 0.05 higher than VIX-absent ({without_mean:.3f}) during a "
            f"vol-spike + breakeven-collapse episode"
        )


# ===========================================================================
# Test 5: RECESSION precedence when sahm_recession=True
# ===========================================================================


class TestRecessionPrecedence:
    """Sahm-flagged days force RECESSION logit to 1.0 (hard override)."""

    def test_recession_logit_is_one_when_sahm_true(self):
        # Inject Sahm=True for a sub-window; the RECESSION logit on
        # those days must be exactly 1.0 (the hard override branch).
        days = 2500
        idx = pd.date_range("2010-01-01", periods=days, freq="D")
        sahm_values = np.zeros(days, dtype=bool)
        sahm_values[2000:2070] = True  # 70-day recession window
        sahm_series = pd.Series(sahm_values, index=idx)

        df = _synthetic_factor_df()
        df["sahm_recession"] = sahm_series

        logits = RulesBasedClassifier().compute_logits(df)
        rec_window = logits.loc[idx[2000]:idx[2069], "RECESSION"]
        assert (rec_window == 1.0).all(), (
            "RECESSION logit must be exactly 1.0 when sahm_recession=True"
        )

    def test_recession_is_top_probability_when_sahm_true(self):
        # On Sahm-True days, RECESSION must be the highest mean prob
        # (or at least in the top-2 across the window).
        days = 2500
        idx = pd.date_range("2010-01-01", periods=days, freq="D")
        sahm_values = np.zeros(days, dtype=bool)
        sahm_values[2000:2070] = True
        df = _synthetic_factor_df()
        df["sahm_recession"] = pd.Series(sahm_values, index=idx)

        probs = RulesBasedClassifier().classify(df)
        rec_window = probs.loc[idx[2010]:idx[2069]]  # skip first 10d edge effects
        mean_probs = rec_window.mean()
        top1 = mean_probs.idxmax()
        assert top1 == "RECESSION", (
            f"RECESSION must be the dominant regime when Sahm fires; got {top1}. "
            f"Mean probs: {mean_probs.to_dict()}"
        )

    def test_recession_logit_zero_when_sahm_false_ism_neutral(self):
        # When Sahm is False AND ISM is at its rolling mean (ism_z = 0),
        # the ISM fallback sigmoid is σ(0, 1.0, 1.5) = 0.182 (non-zero
        # but small).  This test confirms RECESSION is NOT forced to
        # 1.0 when Sahm is False (the override is Sahm-only).
        df = _synthetic_factor_df()
        logits = RulesBasedClassifier().compute_logits(df)
        # No Sahm fires anywhere in _synthetic_factor_df; RECESSION logit
        # should equal the ISM-fallback sigmoid value (not 1.0).
        assert not (logits["RECESSION"] == 1.0).any()


# ===========================================================================
# Test 6: RISK_ON dominant when factors neutral
# ===========================================================================


class TestRiskOnDominantNeutral:
    """With no regime-triggering signal, RISK_ON has the highest mean prob."""

    def test_risk_on_is_top_in_neutral_window(self):
        # Neutral factors: all near their 5y rolling mean -> z-scores
        # near 0 -> all stress-regime sigmoids soft -> RISK_ON residual
        # is highest -> softmax RISK_ON is highest.
        df = _synthetic_factor_df()
        probs = RulesBasedClassifier().classify(df)
        # Slice a window well past the 5y z-score warmup.
        window = probs.loc["2017-01-01":"2018-12-31"]
        mean_probs = window.mean()
        assert mean_probs.idxmax() == "RISK_ON", (
            f"RISK_ON should dominate in a neutral window; got {mean_probs.idxmax()}. "
            f"Mean probs: {mean_probs.to_dict()}"
        )


# ===========================================================================
# Test 7: Determinism
# ===========================================================================


class TestDeterminism:
    """Same input twice -> identical output (no RNG, no LLM, no clock)."""

    def test_two_calls_produce_identical_output(self):
        df = _synthetic_factor_df()
        clf = RulesBasedClassifier()
        out1 = clf.classify(df)
        out2 = clf.classify(df)
        # Byte-identical (assert_frame_equal checks values + index +
        # columns + dtype with no tolerance by default).
        pd.testing.assert_frame_equal(out1, out2)

    def test_two_classifier_instances_produce_identical_output(self):
        # Different instance, same input -> same output (classifier is
        # stateless; thresholds are class-level constants).
        df = _synthetic_factor_df()
        out1 = RulesBasedClassifier().classify(df)
        out2 = RulesBasedClassifier().classify(df)
        pd.testing.assert_frame_equal(out1, out2)

    def test_compute_logits_is_deterministic(self):
        df = _synthetic_factor_df()
        clf = RulesBasedClassifier()
        l1 = clf.compute_logits(df)
        l2 = clf.compute_logits(df)
        pd.testing.assert_frame_equal(l1, l2)


# ===========================================================================
# Per-regime triggering sanity (bonus -- not in spec's required 7,
# but locks in the formula-direction semantics so future threshold
# edits don't accidentally flip a regime's response curve).
# ===========================================================================


class TestRegimeFormulasFire:
    """Each regime formula must respond in the correct direction."""

    def test_inflation_accel_fires_on_rising_breakevens_and_cpi(self):
        days = 2500
        idx = pd.date_range("2010-01-01", periods=days, freq="D")
        df = _synthetic_factor_df()
        # Inject a 60-day window with elevated breakevens + hot CPI.
        df.loc[idx[2000]:idx[2059], "breakeven_10y"] = 3.5
        df.loc[idx[2000]:idx[2059], "cpi_yoy"] = 0.09
        probs = RulesBasedClassifier().classify(df)
        window = probs.loc[idx[2030]:idx[2059]]
        top2 = window.mean().nlargest(2).index.tolist()
        assert "INFLATION_ACCEL" in top2, (
            f"INFLATION_ACCEL should fire on hot breakevens + CPI; top-2 was {top2}"
        )

    def test_real_yield_shock_fires_on_spiking_real_yields(self):
        days = 2500
        idx = pd.date_range("2010-01-01", periods=days, freq="D")
        df = _synthetic_factor_df()
        df.loc[idx[2000]:idx[2059], "real_yield_10y"] = 2.0
        probs = RulesBasedClassifier().classify(df)
        window = probs.loc[idx[2030]:idx[2059]]
        top2 = window.mean().nlargest(2).index.tolist()
        assert "REAL_YIELD_SHOCK" in top2, (
            f"REAL_YIELD_SHOCK should fire on real-yield spike; top-2 was {top2}"
        )


# ===========================================================================
# Tests 8-13: 6-episode live backrun validation (PRIMARY acceptance)
# ===========================================================================


@_SKIP_LIVE
@pytest.mark.live
@pytest.mark.parametrize(
    "start_date,end_date,expected_regime",
    [
        # 1. GFC: Sahm fires 2008-04; RECESSION dominant Sep-08 -> Mar-09.
        ("2008-09-01", "2009-03-31", Regime.RECESSION),
        # 2. COVID: VIX spikes to 80, breakevens collapse Feb -> Apr 2020.
        ("2020-02-01", "2020-04-30", Regime.DEFLATION_SCARE),
        # 3. Inflation breakout: breakevens + CPI surge late 2021 -> mid 2022.
        ("2021-11-01", "2022-06-30", Regime.INFLATION_ACCEL),
        # 4. Fed hiking cycle: real yields spike Jun -> Oct 2022.
        ("2022-06-01", "2022-10-31", Regime.REAL_YIELD_SHOCK),
        # 5. Risk-on year: low vol, stable breakevens, no Sahm in 2019.
        ("2019-01-01", "2019-12-31", Regime.RISK_ON),
        # 6. Risk-on year: post-2022-shock normalisation in 2023.
        ("2023-01-01", "2023-12-31", Regime.RISK_ON),
    ],
    ids=[
        "gfc-recession",
        "covid-deflation-scare",
        "inflation-accel",
        "real-yield-shock",
        "risk-on-2019",
        "risk-on-2023",
    ],
)
def test_backrun_validation(start_date: str, end_date: str, expected_regime: Regime):
    """Each historical episode should classify the expected regime in top-2.

    Acceptance criterion (W3 T12 spec, lines 728-732): the expected
    regime's mean probability across the episode window must be one of
    the top-2 highest among the 5 regimes.  Top-2 (rather than top-1)
    accommodates episodes where two regimes co-fire (e.g. COVID had
    both DEFLATION_SCARE and RECESSION active).

    Requires:
      * ``FRED_API_KEY`` env var (T11 MacroFactorProvider fetches real
        FRED/Yahoo data on first run).
      * ``RUN_LIVE_TESTS=1`` env var to opt in (live tests are skipped
        by default).
    """
    from src.research.macro.factors import MacroFactorProvider

    # Need history BEFORE the earliest episode start so z-scores are
    # well-defined at the start of the window.  Fetch from 1990-01-01
    # to today (single wide cache hit covers all 6 episodes).
    provider = MacroFactorProvider()
    factor_df = provider.load_factors(date(1990, 1, 1), date.today())

    classifier = RulesBasedClassifier()
    probs_df = classifier.classify(factor_df)

    # Slice to the episode window.
    start_ts = pd.Timestamp(start_date)
    end_ts = pd.Timestamp(end_date)
    mask = (probs_df.index >= start_ts) & (probs_df.index <= end_ts)
    episode_probs = probs_df.loc[mask]

    assert not episode_probs.empty, (
        f"No rows in episode window {start_date} -> {end_date}; "
        f"factor_df spans {factor_df.index.min().date()} -> {factor_df.index.max().date()}"
    )

    # Compute mean probability per regime across the episode.
    mean_probs = episode_probs.mean()
    top2 = mean_probs.nlargest(2).index.tolist()

    assert expected_regime.value in top2, (
        f"Episode {start_date} -> {end_date}: expected {expected_regime.value} "
        f"in top-2, got {top2}. Mean probs: {mean_probs.round(4).to_dict()}"
    )


# ===========================================================================
# Test 14: Regime tape generation (live; produces the CSV artefact)
# ===========================================================================


_EVIDENCE_DIR = Path(".omo/evidence")
_TAPE_PATH = _EVIDENCE_DIR / "task-12-regime-tape.csv"


@_SKIP_LIVE
@pytest.mark.live
def test_generate_regime_tape():
    """Generate the 1995-2024 regime tape CSV and assert structural properties.

    Produces ``.omo/evidence/task-12-regime-tape.csv`` with columns
    ``[date, RISK_ON, DEFLATION_SCARE, INFLATION_ACCEL, REAL_YIELD_SHOCK,
    RECESSION, dominant_regime]``.  Acceptance criteria (spec STEP 7):

      * All 5 regimes appear at least once in ``dominant_regime``.
      * RISK_ON is the most common dominant regime (it's the residual
        default; stress regimes are episodic).

    Requires ``FRED_API_KEY`` + ``RUN_LIVE_TESTS=1``.
    """
    from src.research.macro.factors import MacroFactorProvider

    provider = MacroFactorProvider()
    # 1990 start gives the 5y z-score window time to warm up before
    # the 1995-01-01 tape start.  Fetch through end-of-2024 per spec.
    factor_df = provider.load_factors(date(1990, 1, 1), date(2024, 12, 31))

    # Slice to the spec's tape range.
    tape_input = factor_df.loc["1995-01-01":"2024-12-31"].copy()
    assert not tape_input.empty, "factor_df has no rows in 1995-2024"

    tape = generate_regime_tape(tape_input)

    # Structural assertions on the tape frame.
    expected_cols = list(REGIME_COLUMNS) + ["dominant_regime"]
    assert list(tape.columns) == expected_cols
    assert tape["dominant_regime"].dtype == object

    # Write the artefact.
    _EVIDENCE_DIR.mkdir(parents=True, exist_ok=True)
    # CSV format: date as the index (named "date"), then prob columns
    # + dominant_regime.  Use ISO date format for readability.
    tape_to_write = tape.copy()
    tape_to_write.index.name = "date"
    tape_to_write.to_csv(_TAPE_PATH, index=True)

    # All 5 regimes appear at least once as the dominant regime.
    dominant_counts = tape["dominant_regime"].value_counts()
    for regime in REGIME_COLUMNS:
        assert regime in dominant_counts.index, (
            f"Regime {regime} never appears as dominant in the tape; "
            f"counts: {dominant_counts.to_dict()}"
        )

    # RISK_ON is the most common dominant regime.
    assert dominant_counts.idxmax() == "RISK_ON", (
        f"RISK_ON should be the most common dominant regime; got "
        f"{dominant_counts.idxmax()}. Counts: {dominant_counts.to_dict()}"
    )


# ===========================================================================
# Module-level smoke (lets pytest collect even when the live tests
# skip -- ensures import + class instantiation work in the live env)
# ===========================================================================


class TestPublicApiSmoke:
    """Quick contract sanity checks that don't need real data."""

    def test_regime_enum_values_locked(self):
        # The string values are part of the public serialisation
        # contract (LLM prompt schema, regime-tape CSV, cache parquet)
        # and MUST stay byte-identical to narrator.Regime (T13).
        assert Regime.RISK_ON.value == "RISK_ON"
        assert Regime.DEFLATION_SCARE.value == "DEFLATION_SCARE"
        assert Regime.INFLATION_ACCEL.value == "INFLATION_ACCEL"
        assert Regime.REAL_YIELD_SHOCK.value == "REAL_YIELD_SHOCK"
        assert Regime.RECESSION.value == "RECESSION"
        assert len(Regime) == 5

    def test_regime_columns_matches_enum_order(self):
        assert REGIME_COLUMNS == tuple(r.value for r in Regime)

    def test_classifier_instantiates_without_network(self):
        # Constructor must not touch the network (no FredProvider,
        # no YahooProvider, no API keys required).
        clf = RulesBasedClassifier()
        assert clf.ZSCORE_WINDOW_DAYS == 5 * 365

    def test_generate_regime_tape_adds_dominant_column(self):
        df = _synthetic_factor_df(days=2000)
        tape = generate_regime_tape(df)
        assert "dominant_regime" in tape.columns
        # Every row has a non-null dominant regime.
        assert tape["dominant_regime"].notna().all()
        # The dominant regime is one of the 5 enum values.
        assert set(tape["dominant_regime"].unique()).issubset(set(REGIME_COLUMNS))
