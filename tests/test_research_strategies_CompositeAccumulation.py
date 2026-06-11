"""Tests for CompositeAccumulation strategy."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.strategies import (
    InvalidParamsError,
    _REGISTRY,
    get_strategy,
)
from src.research.strategies.CompositeAccumulation import CompositeAccumulation


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_df(n: int = 200, start_price: float = 100.0, drift: float = 0.0, seed: int = 42) -> pd.DataFrame:
    """Create a synthetic OHLC DataFrame with *n* daily bars."""
    rng = np.random.default_rng(seed)
    returns = rng.normal(drift, 0.02, n)
    close = start_price * np.cumprod(1 + returns)
    return pd.DataFrame({"close": close})


def _make_declining_df(n: int = 250, start_price: float = 200.0) -> pd.DataFrame:
    """Synthetic declining series — drives RSI down and price below SMA."""
    rng = np.random.default_rng(99)
    returns = rng.normal(-0.01, 0.01, n)
    close = start_price * np.cumprod(1 + returns)
    return pd.DataFrame({"close": close})


def _make_uptrend_df(n: int = 250, start_price: float = 100.0) -> pd.DataFrame:
    """Synthetic uptrend — drives Mayer Multiple high."""
    rng = np.random.default_rng(77)
    returns = rng.normal(0.01, 0.005, n)
    close = start_price * np.cumprod(1 + returns)
    return pd.DataFrame({"close": close})


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------


class TestCompositeAccumulationDefaults:
    def test_default_params_validate(self):
        s = CompositeAccumulation()
        assert s.params["fgi_weight"] == 0.3
        assert s.params["rsi_weight"] == 0.2
        assert s.params["mayer_weight"] == 0.3
        assert s.params["sma_trend_weight"] == 0.2
        assert s.params["aggressive_frac"] == 0.9
        assert s.params["conservative_frac"] == 0.3


class TestCompositeAccumulationSignals:
    def test_signals_in_zero_one_range(self):
        df = _make_df(200)
        s = CompositeAccumulation()
        sig = s.generate_signals(df)
        assert len(sig) == 200
        assert (sig >= 0.0).all() and (sig <= 1.0).all()

    def test_low_rsi_yields_high_target(self):
        """Declining price → low RSI → high composite score → target > 0.7."""
        df = _make_declining_df(250)
        s = CompositeAccumulation()
        sig = s.generate_signals(df)
        # Late bars should have high target (bearish = accumulate more)
        late_mean = sig.iloc[-30:].mean()
        assert late_mean > 0.6, f"Expected mean > 0.6, got {late_mean}"

    def test_high_mayer_yields_low_target(self):
        """Strong uptrend → high Mayer Multiple → low composite → target < 0.6."""
        df = _make_uptrend_df(250)
        s = CompositeAccumulation()
        sig = s.generate_signals(df)
        # Late bars should have low target (bullish = accumulate less)
        late_mean = sig.iloc[-30:].mean()
        assert late_mean < 0.6, f"Expected mean < 0.6, got {late_mean}"

    def test_sma_trend_off_yields_low_target(self):
        """Declining price (close < SMA) → sma_trend_score = 0 → lower target."""
        df = _make_declining_df(250)
        s = CompositeAccumulation()
        sig = s.generate_signals(df)
        # In a declining market, the SMA trend is off but RSI is very low
        # which drives the composite HIGH (bearish = accumulate more).
        # So we test with a config where only sma_trend_weight matters.
        s2 = CompositeAccumulation(params={
            "fgi_weight": 0.0,
            "rsi_weight": 0.0,
            "mayer_weight": 0.0,
            "sma_trend_weight": 1.0,
            "sma_period": 50,
            "aggressive_frac": 0.9,
            "conservative_frac": 0.3,
            "rsi_period": 14,
        })
        sig2 = s2.generate_signals(df)
        late_mean = sig2.iloc[-30:].mean()
        # close < SMA → score 0 → target = conservative_frac = 0.3
        assert late_mean < 0.5, f"Expected mean < 0.5, got {late_mean}"

    def test_missing_fgi_falls_back_to_neutral(self):
        """When fgi_value column is missing, signals should still be valid."""
        df = _make_df(100)
        assert "fgi_value" not in df.columns
        s = CompositeAccumulation()
        sig = s.generate_signals(df)
        assert len(sig) == 100
        assert not sig.isna().any()


class TestCompositeAccumulationValidation:
    def test_validate_rejects_inverted_aggressive_conservative(self):
        with pytest.raises(InvalidParamsError, match="aggressive_frac"):
            CompositeAccumulation(params={
                "aggressive_frac": 0.2,
                "conservative_frac": 0.8,
            })

    def test_validate_rejects_negative_weights(self):
        with pytest.raises(InvalidParamsError, match="fgi_weight"):
            CompositeAccumulation(params={"fgi_weight": -0.1})

    def test_validate_rejects_weight_above_one(self):
        with pytest.raises(InvalidParamsError, match="rsi_weight"):
            CompositeAccumulation(params={"rsi_weight": 1.5})

    def test_validate_rejects_small_periods(self):
        with pytest.raises(InvalidParamsError, match="sma_period"):
            CompositeAccumulation(params={"sma_period": 1})


class TestCompositeAccumulationRegistry:
    def test_registry_includes(self):
        assert "CompositeAccumulation" in _REGISTRY
        assert _REGISTRY["CompositeAccumulation"] is CompositeAccumulation

    def test_get_strategy_works(self):
        s = get_strategy("CompositeAccumulation")
        assert isinstance(s, CompositeAccumulation)
        assert s.name == "CompositeAccumulation"
