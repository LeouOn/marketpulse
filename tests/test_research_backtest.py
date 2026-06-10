"""Tests for the backtest engine.

The engine must be:
- Deterministic given the same input data + params
- Conservative about fees/slippage (no free trades)
- Correctly compute metrics (CAGR, Sharpe, max DD)
- Handle edge cases (flat series, single bar, BuyAndHold on growing series)
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.research.backtest import (
    BacktestResult,
    cagr,
    calmar_ratio,
    hit_rate,
    max_drawdown_pct,
    profit_factor,
    run_backtest,
    run_backtest_from_names,
    sharpe_ratio,
    sortino_ratio,
)
from src.research.scaling import FixedDollar, VolatilityTargeted
from src.research.strategies import (
    BuyAndHold,
    DCAFixedAmount,
    MomentumTrend,
    NoTrade,
)


# ---------------------------------------------------------------------------
# Synthetic series
# ---------------------------------------------------------------------------


def _flat(n: int = 100, price: float = 100.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1.0,
        }
    )


def _growing(n: int = 365, start: float = 100.0, end: float = 200.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": np.linspace(start, end, n),
            "high": np.linspace(start, end, n) + 1,
            "low": np.linspace(start, end, n) - 1,
            "close": np.linspace(start, end, n),
            "volume": 1.0,
        }
    )


def _halving(n: int = 365) -> pd.DataFrame:
    """Price halves linearly from 100 to 50."""
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": np.linspace(100.0, 50.0, n),
            "high": np.linspace(100.0, 50.0, n) + 1,
            "low": np.linspace(100.0, 50.0, n) - 1,
            "close": np.linspace(100.0, 50.0, n),
            "volume": 1.0,
        }
    )


# ---------------------------------------------------------------------------
# Metrics helpers
# ---------------------------------------------------------------------------


def test_cagr_grows_at_expected_rate():
    # 100 -> 200 over 1 year -> 100% CAGR
    assert cagr(100.0, 200.0, 1.0) == pytest.approx(1.0, abs=1e-9)
    # 100 -> 121 over 2 years -> 10% CAGR
    assert cagr(100.0, 121.0, 2.0) == pytest.approx(0.10, abs=1e-9)


def test_cagr_handles_degenerate_inputs():
    assert cagr(100.0, 100.0, 0.0) == 0.0
    assert cagr(0.0, 100.0, 1.0) == 0.0
    assert cagr(100.0, 0.0, 1.0) == 0.0


def test_max_drawdown_pct_known_series():
    s = pd.Series([100.0, 50.0, 75.0, 60.0, 100.0])
    assert max_drawdown_pct(s) == pytest.approx(-50.0, abs=1e-9)


def test_max_drawdown_pct_no_drawdown():
    s = pd.Series([100.0, 110.0, 120.0, 130.0])
    assert max_drawdown_pct(s) == 0.0


def test_sharpe_ratio_zero_when_constant():
    s = pd.Series([0.01] * 100)
    assert sharpe_ratio(s) == 0.0


def test_sharpe_ratio_positive_on_winning_series():
    # Strictly positive returns -> positive Sharpe
    s = pd.Series(np.full(200, 0.005))
    assert sharpe_ratio(s) == 0.0  # std=0 -> 0
    s = pd.Series(np.random.default_rng(0).normal(0.005, 0.01, 500))
    assert sharpe_ratio(s) > 0


def test_sortino_ratio_undefined_when_no_downside():
    s = pd.Series([0.01] * 100)
    assert sortino_ratio(s) == 0.0


def test_calmar_ratio_normal():
    # 100 -> 200 in 1 year, 50% max DD -> Calmar = 1.0/0.5 = 2.0
    assert calmar_ratio(100.0, 200.0, 1.0, -50.0) == pytest.approx(2.0, abs=1e-9)


def test_calmar_ratio_zero_dd_returns_zero():
    assert calmar_ratio(100.0, 200.0, 1.0, 0.0) == 0.0


# ---------------------------------------------------------------------------
# Profit factor / hit rate
# ---------------------------------------------------------------------------


def test_profit_factor_no_trades_is_zero():
    assert profit_factor([]) == 0.0


def test_hit_rate_no_trades_is_zero():
    assert hit_rate([]) == 0.0


# ---------------------------------------------------------------------------
# Engine: edge cases
# ---------------------------------------------------------------------------


def test_empty_df_raises():
    with pytest.raises(ValueError):
        run_backtest(pd.DataFrame(), BuyAndHold())


def test_df_missing_close_raises():
    df = pd.DataFrame({"ts": pd.date_range("2024-01-01", periods=10, freq="D")})
    with pytest.raises(ValueError):
        run_backtest(df, BuyAndHold())


def test_single_bar_buy_and_hold_buys_and_holds():
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=1, freq="D"),
            "open": [100.0],
            "high": [100.0],
            "low": [100.0],
            "close": [100.0],
            "volume": [1.0],
        }
    )
    result = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    # After 1 bar, all equity is in BTC at 100 -> ending_equity == starting
    assert result.ending_equity == pytest.approx(10_000.0, abs=1e-6)
    assert result.metrics["num_buys"] == 1
    assert result.metrics["num_sells"] == 0


# ---------------------------------------------------------------------------
# Engine: BuyAndHold on growing series
# ---------------------------------------------------------------------------


def test_buy_and_hold_growing_doubles_equity():
    df = _growing(n=365, start=100.0, end=200.0)
    result = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    # 100 -> 200 = 100% total return
    assert result.metrics["total_return_pct"] == pytest.approx(100.0, abs=0.1)
    # 1-year CAGR ~= 100% (slightly > 100% because 365 days is < 365.25)
    assert 99.0 < result.metrics["cagr_pct"] < 102.0
    # No drawdown on a monotonically rising series
    assert result.metrics["max_drawdown_pct"] == pytest.approx(0.0, abs=0.01)


def test_buy_and_hold_with_fees_loses_money_to_costs():
    """On a flat series, fees alone should produce a loss."""
    df = _flat(n=30, price=100.0)
    result = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=10, slippage_bps=0)
    # Bought once at the open. Fee = 10_000 * 0.001 = $10.
    # Ending equity = starting - fee = $9,990.
    assert result.ending_equity == pytest.approx(9_990.0, abs=0.01)


# ---------------------------------------------------------------------------
# Engine: NoTrade
# ---------------------------------------------------------------------------


def test_no_trade_keeps_cash_unchanged():
    df = _growing(n=100, start=100.0, end=200.0)
    result = run_backtest(df, NoTrade(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    # No buys -> equity == starting
    assert result.ending_equity == 10_000.0
    assert result.metrics["num_buys"] == 0
    assert result.metrics["num_trades"] == 0


# ---------------------------------------------------------------------------
# Engine: DCA
# ---------------------------------------------------------------------------


def test_dca_fixed_amount_buys_periodically():
    df = _flat(n=70, price=100.0)
    # $100 every 7 bars for 70 bars = 10 buys of $100 each = $1000 spent
    strategy = DCAFixedAmount(params={"amount_usd": 100.0, "every_n_bars": 7})
    result = run_backtest(df, strategy, starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    # 70/7 = 10 buy days
    assert result.metrics["num_buys"] == 10
    # Total spent = 10 * 100 = $1000 (cash reduced by ~1000)
    # Total equity should be 10_000 - 1000 (spent) + 1000 (held as BTC) = 10_000
    assert result.ending_equity == pytest.approx(10_000.0, abs=1.0)


def test_dca_growing_price_underperforms_buy_and_hold():
    """DCA on a rising series should underperform lump-sum BuyAndHold."""
    df = _growing(n=365, start=100.0, end=300.0)
    bh = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    dca = run_backtest(
        df,
        DCAFixedAmount(params={"amount_usd": 50.0, "every_n_bars": 7}),
        starting_equity=10_000.0,
        fee_bps=0,
        slippage_bps=0,
    )
    # Both should be positive; BH should be higher because it captures full run-up
    assert bh.ending_equity > dca.ending_equity
    assert bh.metrics["total_return_pct"] > dca.metrics["total_return_pct"]


# ---------------------------------------------------------------------------
# Engine: momentum
# ---------------------------------------------------------------------------


def test_momentum_outperforms_buy_hold_during_halving():
    """In a halved market, going to cash should preserve capital."""
    df = _halving(n=400)
    bh = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    mom = run_backtest(
        df, MomentumTrend(params={"sma_period": 50}), starting_equity=10_000.0, fee_bps=0, slippage_bps=0
    )
    # BH halves; Momentum should de-risk at some point and end higher
    assert mom.ending_equity > bh.ending_equity
    # BH should have ~-50% return
    assert bh.metrics["total_return_pct"] < -40.0
    # Momentum should be less negative
    assert mom.metrics["total_return_pct"] > bh.metrics["total_return_pct"]


# ---------------------------------------------------------------------------
# Engine: scaling model integration
# ---------------------------------------------------------------------------


def test_vol_targeted_scaling_doesnt_break_engine():
    df = _growing(n=200)
    result = run_backtest(
        df,
        BuyAndHold(),
        scaling=VolatilityTargeted(params={"target_annual_vol": 0.20}),
        starting_equity=10_000.0,
        fee_bps=10,
        slippage_bps=5,
    )
    # Should still produce a positive return on a growing series
    assert result.ending_equity > 10_000.0
    assert result.metrics["num_trades"] >= 1


# ---------------------------------------------------------------------------
# Engine: determinism
# ---------------------------------------------------------------------------


def test_engine_is_deterministic():
    df = _growing(n=200, start=100.0, end=200.0)
    a = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=10, slippage_bps=5)
    b = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=10, slippage_bps=5)
    assert a.metrics == b.metrics
    assert (a.equity_curve == b.equity_curve).all()


# ---------------------------------------------------------------------------
# Engine: from-names convenience
# ---------------------------------------------------------------------------


def test_run_backtest_from_names():
    df = _growing(n=100)
    result = run_backtest_from_names(
        df,
        strategy_name="BuyAndHold",
        scaling_name="FixedDollar",
        scaling_params={"amount_usd": 100.0},
        starting_equity=10_000.0,
    )
    assert result.strategy_name == "BuyAndHold"
    assert result.scaling_name == "FixedDollar"


def test_run_backtest_from_names_unknown_strategy_raises():
    df = _growing(n=10)
    with pytest.raises(KeyError):
        run_backtest_from_names(df, strategy_name="NotARealStrategy")
