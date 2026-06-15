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
    Deposit,
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
    strategy = DCAFixedAmount(params={"amount_usd": 100.0, "every_n_bars": 7})
    # With FixedDollar($100), scaling caps each buy at $100 regardless of equity
    scaling = FixedDollar(params={"amount_usd": 100.0})
    result = run_backtest(
        df, strategy, scaling=scaling,
        starting_equity=10_000.0, fee_bps=0, slippage_bps=0,
    )
    # 70/7 = 10 buy days × $100 = $1,000 total deployed
    assert result.metrics["num_buys"] == 10
    # On flat price, equity stays at $10,000 ($9,000 cash + $1,000 BTC)
    assert result.ending_equity == pytest.approx(10_000.0, abs=1.0)


def test_dca_growing_price_underperforms_buy_and_hold():
    """DCA on a rising series should underperform lump-sum BuyAndHold."""
    df = _growing(n=365, start=100.0, end=300.0)
    bh = run_backtest(df, BuyAndHold(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0)
    dca = run_backtest(
        df,
        DCAFixedAmount(params={"amount_usd": 50.0, "every_n_bars": 7}),
        scaling=FixedDollar(params={"amount_usd": 50.0}),
        starting_equity=10_000.0,
        fee_bps=0,
        slippage_bps=0,
    )
    # BH goes all-in at $100, DCA dribbles in at higher prices → BH wins
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


# ---------------------------------------------------------------------------
# F1: profit_factor capped at 999.0
# ---------------------------------------------------------------------------


def test_profit_factor_no_losses_no_inf():
    """When there are only wins and no losses, profit_factor should be 999.0, not inf."""
    from src.research.backtest import Trade

    # Construct trades that produce all-positive cash flows (no losses).
    # A sell with avg_cost=0 (no prior buy) produces realized = notional.
    trades = [
        Trade(
            ts=pd.Timestamp("2024-01-02"),
            side="sell",
            btc_amount=0.5,
            price=200.0,
            notional_usd=100.0,
            fee_usd=0.0,
            slippage_usd=0.0,
            cash_after=10100.0,
            btc_after=0.0,
            equity_after=10100.0,
        ),
    ]
    pf = profit_factor(trades)
    assert pf == 999.0
    # Must be JSON-serializable (finite)
    assert math.isfinite(pf)


def test_profit_factor_profitable_closed_trade_above_one():
    """A profitable buy→sell must yield profit_factor > 1.0.

    Regression test: the old implementation mixed cash outflows (buys) with
    realized PnL (sells), so every buy counted as a "loss" and made
    profit_factor meaningless for DCA strategies (e.g. buy $100 / sell for
    $150 used to return ~0.45 instead of 999.0 / a large number).
    """
    from src.research.backtest import Trade

    # Buy 1 BTC at $100 (cost basis = $100), then sell 1 BTC at $150.
    # Realized PnL = $150 - $0 fee - $0 slip - $100 cost = +$50 (win, no loss).
    trades = [
        Trade(
            ts=pd.Timestamp("2024-01-01"),
            side="buy",
            btc_amount=1.0,
            price=100.0,
            notional_usd=100.0,
            fee_usd=0.0,
            slippage_usd=0.0,
            cash_after=9900.0,
            btc_after=1.0,
            equity_after=10000.0,
        ),
        Trade(
            ts=pd.Timestamp("2024-01-02"),
            side="sell",
            btc_amount=1.0,
            price=150.0,
            notional_usd=150.0,
            fee_usd=0.0,
            slippage_usd=0.0,
            cash_after=10150.0,
            btc_after=0.0,
            equity_after=10150.0,
        ),
    ]
    pf = profit_factor(trades)
    assert pf > 1.0, f"profitable closed trade should have profit_factor > 1.0, got {pf}"
    assert pf == 999.0  # wins only, no losses -> capped at 999.0
    # hit_rate should be 100% on the single profitable closed trade
    assert hit_rate(trades) == pytest.approx(1.0, abs=1e-9)


def test_profit_factor_losing_closed_trade_below_one():
    """An unprofitable buy→sell must yield profit_factor < 1.0 (or 0)."""
    from src.research.backtest import Trade

    # Buy 1 BTC at $100, sell 1 BTC at $80 -> realized PnL = -$20 (loss).
    trades = [
        Trade(
            ts=pd.Timestamp("2024-01-01"),
            side="buy",
            btc_amount=1.0,
            price=100.0,
            notional_usd=100.0,
            fee_usd=0.0,
            slippage_usd=0.0,
            cash_after=9900.0,
            btc_after=1.0,
            equity_after=10000.0,
        ),
        Trade(
            ts=pd.Timestamp("2024-01-02"),
            side="sell",
            btc_amount=1.0,
            price=80.0,
            notional_usd=80.0,
            fee_usd=0.0,
            slippage_usd=0.0,
            cash_after=9980.0,
            btc_after=0.0,
            equity_after=9980.0,
        ),
    ]
    pf = profit_factor(trades)
    # Only losses, no wins -> 0.0 (per the no-wins branch of the cap)
    assert pf == 0.0
    assert hit_rate(trades) == pytest.approx(0.0, abs=1e-9)


# ---------------------------------------------------------------------------
# F19: zero-price bar preserves BTC equity
# ---------------------------------------------------------------------------


def test_zero_price_bar_preserves_btc_equity():
    """A zero-price bar should not wipe BTC equity to cash-only."""
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=4, freq="D"),
            "open": [50000.0, 50000.0, 0.0, 50000.0],
            "high": [50000.0, 50000.0, 0.0, 50000.0],
            "low": [50000.0, 50000.0, 0.0, 50000.0],
            "close": [50000.0, 0.0, 0.0, 50000.0],
            "volume": [1.0, 1.0, 0.0, 1.0],
        }
    )
    # BuyAndHold buys on bar 0 at $50k, holding 0.2 BTC.
    # Bar 1 has close=0 (degenerate), equity should use last valid price ($50k).
    result = run_backtest(
        df, BuyAndHold(), starting_equity=10_000.0, fee_bps=0, slippage_bps=0,
    )
    # Equity on bar 1 (zero-price) should reflect BTC at last valid price, not 0.
    assert result.equity_curve.iloc[1] > 0
    # It should be close to the starting equity (since price didn't change from bar 0).
    assert result.equity_curve.iloc[1] == pytest.approx(10_000.0, abs=100.0)


# ---------------------------------------------------------------------------
# Wave 3: recurring cash inflows
# ---------------------------------------------------------------------------


def test_recurring_inflows_every_n_bars():
    """$500 deposited every 30 bars on a flat price series."""
    df = _flat(n=120, price=100.0)
    result = run_backtest(
        df, NoTrade(), starting_equity=0.0, fee_bps=0, slippage_bps=0,
        inflows=[{"every_n_bars": 30, "amount_usd": 500.0, "source": "monthly_salary"}],
    )
    # Deposits at bars 0, 30, 60, 90 = 4 deposits × $500 = $2000
    assert len(result.deposits) == 4
    assert all(d.amount_usd == 500.0 for d in result.deposits)
    assert all(d.source == "monthly_salary" for d in result.deposits)
    # Cash should equal total deposited since NoTrade buys nothing
    assert result.ending_equity == pytest.approx(2_000.0, abs=0.01)


def test_inflows_dont_apply_fees():
    """Deposits should add exactly amount_usd to cash — no fees."""
    df = _flat(n=60, price=100.0)
    result = run_backtest(
        df, NoTrade(), starting_equity=0.0, fee_bps=50.0, slippage_bps=10.0,
        inflows=[{"every_n_bars": 30, "amount_usd": 500.0}],
    )
    # 2 deposits × $500 = $1000. Fees/slippage should NOT be applied.
    assert len(result.deposits) == 2
    assert result.ending_equity == pytest.approx(1_000.0, abs=0.01)


def test_inflows_with_zero_starting_equity():
    """Deposits should fund the entire portfolio when starting_equity=0."""
    df = _flat(n=31, price=100.0)
    result = run_backtest(
        df, BuyAndHold(), starting_equity=0.0, fee_bps=0, slippage_bps=0,
        inflows=[{"every_n_bars": 30, "amount_usd": 1_000.0}],
    )
    # Bar 0: starting_equity=0, no deposit yet at bar 0? Actually bar 0 triggers
    # because 0 % 30 == 0. So bar 0: deposit $1000, then BuyAndHold buys BTC.
    # On flat price, ending equity should equal the deposit minus any trade costs.
    # With fee_bps=0 and slippage_bps=0, ending equity = $1000.
    assert len(result.deposits) >= 1
    # Total deposited should be either $1000 (bar 0 only, since 30 doesn't trigger for i=30 in 31 bars)
    # Actually bar 30: i=30, 30 % 30 == 0, so deposit at i=0 and i=30 = 2 deposits
    assert result.metrics["total_deposited"] == pytest.approx(2_000.0, abs=0.01)
    # BuyAndHold should buy on bar 0 and bar 30 with the deposited cash
    assert result.ending_equity > 0


def test_total_deposited_in_metrics():
    """metrics['total_deposited'] should equal the sum of all deposit amounts."""
    df = _flat(n=91, price=100.0)
    result = run_backtest(
        df, NoTrade(), starting_equity=0.0, fee_bps=0, slippage_bps=0,
        inflows=[
            {"every_n_bars": 30, "amount_usd": 500.0, "source": "salary"},
            {"day_of_month": 15, "amount_usd": 200.0, "source": "bonus"},
        ],
    )
    # Verify metric exists and equals sum
    assert "total_deposited" in result.metrics
    assert "num_deposits" in result.metrics
    total = sum(d.amount_usd for d in result.deposits)
    assert result.metrics["total_deposited"] == pytest.approx(total, abs=0.01)
    assert result.metrics["num_deposits"] == len(result.deposits)


# ---------------------------------------------------------------------------
# Wave 4: on-chain state wiring
# ---------------------------------------------------------------------------


def test_state_dict_has_mvrv_key(monkeypatch):
    """Backtest engine should set state['mvrv_z'] when on-chain data is loaded."""
    # Mock fetch_mvrv to return known data matching our test dates
    _mock_mvrv = pd.DataFrame({
        "ts": [pd.Timestamp("2024-01-01"), pd.Timestamp("2024-01-02")],
        "mvrv_z": [1.5, 2.0],
    })
    monkeypatch.setattr(
        "src.research.data.on_chain.fetch_mvrv",
        lambda force=False: _mock_mvrv,
    )
    # We can't directly inspect state inside the engine, but we can verify
    # that the OnChainGated scaling model receives the correct mvrv_z values
    # by checking that trades are executed correctly.
    from src.research.scaling.OnChainGated import OnChainGated

    df = _flat(n=2, price=100.0)
    # Use OnChainGated so the state["mvrv_z"] value is consumed
    scaling = OnChainGated(params={"base_buy_multiplier": 100.0})
    result = run_backtest(
        df, BuyAndHold(), scaling=scaling, starting_equity=10_000.0,
        fee_bps=0, slippage_bps=0,
    )
    # If mvrv_z=1.5 was loaded, OnChainGated uses multiplier 0.75
    # (1.5 < 3.0 band → 0.75 multiplier → 100 * 0.75 = 75)
    # The engine should have at least one buy trade with the scaled amount
    assert len(result.trades) >= 1
    first_buy = [t for t in result.trades if t.side == "buy"][0]
    assert first_buy.notional_usd == pytest.approx(75.0, abs=0.01)


# ---------------------------------------------------------------------------
# F23/F24/F28: negative-parameter validation guards
# ---------------------------------------------------------------------------


def test_negative_starting_equity_rejected():
    """Negative starting_equity must raise a clear ValueError."""
    df = _growing(n=10)
    with pytest.raises(ValueError, match="starting_equity must be >= 0"):
        run_backtest(df, BuyAndHold(), starting_equity=-1000)


def test_negative_fee_bps_rejected():
    """Negative fee_bps must raise a clear ValueError."""
    df = _growing(n=10)
    with pytest.raises(ValueError, match="fee_bps must be >= 0"):
        run_backtest(df, BuyAndHold(), fee_bps=-5)


def test_negative_slippage_bps_rejected():
    """Negative slippage_bps must raise a clear ValueError."""
    df = _growing(n=10)
    with pytest.raises(ValueError, match="slippage_bps must be >= 0"):
        run_backtest(df, BuyAndHold(), slippage_bps=-5)
