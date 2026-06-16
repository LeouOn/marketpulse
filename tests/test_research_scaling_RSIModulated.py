"""Tests for RSIModulated scaling model."""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.research.scaling.RSIModulated import RSIModulated


def _returns(n: int = 200, seed: int = 0) -> pd.Series:
    rng = np.random.default_rng(seed)
    return pd.Series(rng.normal(0.001, 0.02, n))


def _size(rsi: float | None, *, base: float = 1.0) -> tuple[float, float]:
    """Helper: instantiate model and call size() with the given RSI value."""
    model = RSIModulated(params={"base_buy_multiplier": base})
    state = {"rsi_14": rsi} if rsi is not None else {}
    return model.size(
        equity=10_000,
        position_value=0,
        price=30_000,
        recent_returns=_returns(),
        state=state,
    )


# ---------------------------------------------------------------------------
# Test cases
# ---------------------------------------------------------------------------


def test_rsi_30_triggers_1_5x():
    """RSI=20 (deeply oversold) → weight=1.5"""
    buy, sell = _size(20.0)
    assert buy == 1.5
    assert sell == 0.0


def test_rsi_50_returns_1_0x():
    """RSI=45 (neutral zone) → weight=1.0"""
    buy, sell = _size(45.0)
    assert buy == 1.0
    assert sell == 0.0


def test_rsi_70_returns_0_5x():
    """RSI=80 (overbought) → weight=0.5"""
    buy, sell = _size(80.0)
    assert buy == 0.5
    assert sell == 0.0


def test_rsi_none_falls_back_to_1_0():
    """Missing rsi_14 in state → weight=1.0 fallback"""
    model = RSIModulated()
    buy, sell = model.size(
        equity=10_000,
        position_value=0,
        price=30_000,
        recent_returns=_returns(),
        state=None,
    )
    assert buy == 1.0
    assert sell == 0.0


def test_rsi_boundary_30():
    """RSI exactly 30 falls into the 30-50 bracket → weight=1.0"""
    buy, sell = _size(30.0)
    assert buy == 1.0
    assert sell == 0.0


def test_rsi_boundary_70():
    """RSI exactly 70 falls into the ≥70 bracket → weight=0.5"""
    buy, sell = _size(70.0)
    assert buy == 0.5
    assert sell == 0.0


def test_rsi_nan_falls_back_to_1_0():
    """NaN rsi_14 → weight=1.0 fallback"""
    buy, sell = _size(float("nan"))
    assert buy == 1.0
    assert sell == 0.0
