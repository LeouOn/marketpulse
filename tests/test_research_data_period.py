"""Tests for ``trading_days_per_year`` parameterization of ``data_summary`` and
``run_backtest`` (W1 T4).

Background
----------
The BTC research lab hardcodes ``365.25`` (crypto trades every day) as the
sqrt-N annualization factor for vol / Sharpe / Sortino. For multi-asset support
(housing = 12 periods/yr, equities = 252) that factor must be a parameter.

These tests verify:
- ``data_summary`` scales ``realized_vol_annual_pct`` by ``sqrt(trading_days_per_year)``
- ``run_backtest`` scales Sharpe/Sortino by ``sqrt(trading_days_per_year)``
- CAGR (true calendar years) is UNAFFECTED by ``trading_days_per_year``
- Defaults preserve BTC behavior exactly
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.research.backtest import run_backtest
from src.research.data import data_summary
from src.research.strategies import BuyAndHold


# ---------------------------------------------------------------------------
# Synthetic price data
# ---------------------------------------------------------------------------


def _noisy_growing(n: int = 400, start: float = 100.0, drift: float = 0.0005,
                   vol: float = 0.02, seed: int = 0) -> pd.DataFrame:
    """Daily price series with positive drift + noise so Sharpe/Sortino are meaningful."""
    rng = np.random.default_rng(seed)
    log_rets = rng.normal(drift, vol, n)
    close = start * np.exp(np.cumsum(log_rets))
    return pd.DataFrame(
        {
            "ts": pd.date_range("2020-01-01", periods=n, freq="D"),
            "open": close,
            "high": close * 1.001,
            "low": close * 0.999,
            "close": close,
            "volume": 1.0,
        }
    )


# ---------------------------------------------------------------------------
# data_summary
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tdpy", [12, 252, 365.25])
def test_data_summary_accepts_trading_days_per_year(tdpy):
    df = _noisy_growing()
    summary = data_summary(df, trading_days_per_year=tdpy)
    assert "realized_vol_annual_pct" in summary
    assert summary["realized_vol_annual_pct"] > 0


def test_data_summary_vol_scales_with_sqrt_of_trading_days_per_year():
    """realized_vol_annual_pct must equal std * sqrt(tdpy) * 100."""
    df = _noisy_growing(seed=5)
    s_btc = data_summary(df, trading_days_per_year=365.25)
    s_housing = data_summary(df, trading_days_per_year=12)
    ratio = s_btc["realized_vol_annual_pct"] / s_housing["realized_vol_annual_pct"]
    expected_ratio = math.sqrt(365.25 / 12)
    assert ratio == pytest.approx(expected_ratio, rel=1e-9)


def test_data_summary_cagr_unaffected_by_trading_days_per_year():
    """CAGR uses true calendar years (elapsed days / 365.25); must not depend on tdpy."""
    df = _noisy_growing(seed=9)
    s_btc = data_summary(df, trading_days_per_year=365.25)
    s_housing = data_summary(df, trading_days_per_year=12)
    s_eq = data_summary(df, trading_days_per_year=252)
    assert s_btc["cagr_pct"] == s_housing["cagr_pct"] == s_eq["cagr_pct"]
    assert s_btc["total_return_pct"] == s_housing["total_return_pct"]


def test_data_summary_default_preserves_btc_behavior():
    df = _noisy_growing(seed=1)
    s_default = data_summary(df)
    s_explicit = data_summary(df, trading_days_per_year=365.25)
    assert s_default == s_explicit


# ---------------------------------------------------------------------------
# run_backtest
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("tdpy", [12, 252, 365.25])
def test_run_backtest_accepts_trading_days_per_year(tdpy):
    df = _noisy_growing(n=300)
    result = run_backtest(df, BuyAndHold(), trading_days_per_year=tdpy)
    assert "sharpe" in result.metrics
    assert "sortino" in result.metrics
    assert math.isfinite(result.metrics["sharpe"])
    assert math.isfinite(result.metrics["sortino"])


def test_run_backtest_sharpe_sortino_scale_with_trading_days_per_year():
    """Sharpe/Sortino scale as sqrt(periods_per_year) — the Metis A5 bug fix.

    Without the fix, run_backtest silently used the 365.25 default inside
    sharpe_ratio/sortino_ratio, so housing (12/yr) metrics were wrong by
    sqrt(365.25/12) ~= 5.5x.
    """
    df = _noisy_growing(n=400, seed=42)
    res_btc = run_backtest(df, BuyAndHold(), trading_days_per_year=365.25)
    res_housing = run_backtest(df, BuyAndHold(), trading_days_per_year=12)
    # Sharpe must scale as sqrt(tdpy ratio).
    expected_ratio = math.sqrt(365.25 / 12)
    actual_sharpe_ratio = res_btc.metrics["sharpe"] / res_housing.metrics["sharpe"]
    assert actual_sharpe_ratio == pytest.approx(expected_ratio, rel=1e-6)
    actual_sortino_ratio = res_btc.metrics["sortino"] / res_housing.metrics["sortino"]
    assert actual_sortino_ratio == pytest.approx(expected_ratio, rel=1e-6)


def test_run_backtest_cagr_unaffected_by_trading_days_per_year():
    """CAGR is calendar-based; must not change with tdpy."""
    df = _noisy_growing(n=400, seed=8)
    res_btc = run_backtest(df, BuyAndHold(), trading_days_per_year=365.25)
    res_housing = run_backtest(df, BuyAndHold(), trading_days_per_year=12)
    assert res_btc.metrics["cagr_pct"] == res_housing.metrics["cagr_pct"]
    assert res_btc.metrics["total_return_pct"] == res_housing.metrics["total_return_pct"]
    assert res_btc.metrics["years"] == res_housing.metrics["years"]


def test_run_backtest_default_preserves_btc_behavior():
    """Default (omitted param) must equal explicit 365.25 to full precision."""
    df = _noisy_growing(n=400, seed=13)
    res_default = run_backtest(df, BuyAndHold())
    res_explicit = run_backtest(df, BuyAndHold(), trading_days_per_year=365.25)
    # Every metric must be identical (regression guard).
    assert res_default.metrics == res_explicit.metrics
