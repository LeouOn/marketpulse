"""Tests for src/research/scaling/SentimentModulated.py."""

from __future__ import annotations

import math

import pandas as pd
import pytest

from src.research.scaling.SentimentModulated import SentimentModulated


EQUITY = 10_000.0


def _state(fgi: float | None) -> dict | None:
    if fgi is None:
        return None
    return {"fgi_value": fgi}


def _size(fgi: float | None) -> float:
    """Helper: compute buy_usd for a given FGI value."""
    model = SentimentModulated()
    buy_usd, sell_usd = model.size(
        equity=EQUITY,
        position_value=0.0,
        price=50_000.0,
        recent_returns=pd.Series([0.01, -0.01, 0.02]),
        state=_state(fgi),
    )
    assert sell_usd == 0.0
    return buy_usd


# Expected: base_buy_multiplier=1.0 → buy = equity * 1.0 * multiplier
class TestSentimentModulated:
    def test_fgi_extreme_fear(self):
        """FGI=10 → multiplier=1.5 → buy = equity * 1.5."""
        assert _size(10) == pytest.approx(EQUITY * 1.5)

    def test_fgi_fear(self):
        """FGI=30 → multiplier=1.0 → buy = equity * 1.0."""
        assert _size(30) == pytest.approx(EQUITY * 1.0)

    def test_fgi_neutral(self):
        """FGI=50 → multiplier=0.75 → buy = equity * 0.75."""
        assert _size(50) == pytest.approx(EQUITY * 0.75)

    def test_fgi_greed(self):
        """FGI=65 → multiplier=0.5 → buy = equity * 0.5."""
        assert _size(65) == pytest.approx(EQUITY * 0.5)

    def test_fgi_extreme_greed(self):
        """FGI=90 → multiplier=0.25 → buy = equity * 0.25."""
        assert _size(90) == pytest.approx(EQUITY * 0.25)

    def test_fgi_none_falls_back(self):
        """state=None → multiplier=1.0 → buy = equity * 1.0."""
        assert _size(None) == pytest.approx(EQUITY * 1.0)

    def test_fgi_boundary_25(self):
        """FGI=25 → multiplier=1.0 (fear band, not extreme fear)."""
        assert _size(25) == pytest.approx(EQUITY * 1.0)

    def test_fgi_boundary_75(self):
        """FGI=75 → multiplier=0.25 (extreme greed)."""
        assert _size(75) == pytest.approx(EQUITY * 0.25)

    def test_fgi_nan_falls_back(self):
        """FGI=NaN → multiplier=1.0."""
        assert _size(float("nan")) == pytest.approx(EQUITY * 1.0)

    def test_fgi_missing_key_falls_back(self):
        """state without fgi_value key → multiplier=1.0."""
        model = SentimentModulated()
        buy_usd, sell_usd = model.size(
            equity=EQUITY,
            position_value=0.0,
            price=50_000.0,
            recent_returns=pd.Series([0.01]),
            state={"other_key": 42},
        )
        assert buy_usd == pytest.approx(EQUITY * 1.0)
        assert sell_usd == 0.0

    def test_custom_base_multiplier(self):
        """Custom base_buy_multiplier scales correctly."""
        model = SentimentModulated(params={"base_buy_multiplier": 2.0})
        buy_usd, sell_usd = model.size(
            equity=EQUITY,
            position_value=0.0,
            price=50_000.0,
            recent_returns=pd.Series([0.01]),
            state={"fgi_value": 10},  # extreme fear → 1.5
        )
        # 10_000 * 2.0 * 1.5 = 30_000
        assert buy_usd == pytest.approx(EQUITY * 2.0 * 1.5)
