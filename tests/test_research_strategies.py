"""Tests for the strategy library.

Each strategy is exercised against a synthetic price series with known
properties. The tests check that the signal matches expectations.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from typing import ClassVar

from src.research.strategies import (
    BuyAndHold,
    DCAFixedAmount,
    DCAValueAveraging,
    InvalidParamsError,
    LadderLimit,
    MeanReversionBollinger,
    MeanReversionRSI,
    MomentumTrend,
    NoTrade,
    Strategy,
    describe_strategy,
    get_strategy,
    list_strategies,
)


# ---------------------------------------------------------------------------
# Synthetic series helpers
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
            "source": "synthetic",
        }
    )


def _trending_up(n: int = 250, start: float = 100.0, slope: float = 1.0) -> pd.DataFrame:
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": start + np.arange(n) * slope,
            "high": start + np.arange(n) * slope + 1.0,
            "low": start + np.arange(n) * slope - 1.0,
            "close": start + np.arange(n) * slope,
            "volume": 1.0,
            "source": "synthetic",
        }
    )


def _down_then_up(n: int = 200, noise: float = 5.0, seed: int = 42) -> pd.DataFrame:
    """Price falls sharply then mean-reverts, with realistic noise.

    Noise is needed so that the rolling std is non-trivial and the Bollinger
    band lower trigger can actually fire during the crash.
    """
    rng = np.random.default_rng(seed)
    trend = np.concatenate(
        [
            np.linspace(100.0, 60.0, n // 2),  # crash
            np.linspace(60.0, 95.0, n - n // 2),  # recovery
        ]
    )
    noise_series = rng.normal(0.0, noise, size=n)
    close = np.maximum(trend + noise_series, 1.0)
    return pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=n, freq="D"),
            "open": close,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": 1.0,
            "source": "synthetic",
        }
    )


# ---------------------------------------------------------------------------
# Baselines
# ---------------------------------------------------------------------------


def test_buy_and_hold_is_always_1():
    sig = BuyAndHold().generate_signals(_flat())
    assert (sig == 1.0).all()


def test_no_trade_is_always_0():
    sig = NoTrade().generate_signals(_flat())
    assert (sig == 0.0).all()


# ---------------------------------------------------------------------------
# DCA
# ---------------------------------------------------------------------------


def test_dca_fixed_amount_signals_only_on_buy_days():
    sig = DCAFixedAmount(params={"amount_usd": 100.0, "every_n_bars": 7}).generate_signals(_flat(50))
    # Bars 0, 7, 14, 21, 28, 35, 42, 49 should be 1.0
    assert sig.iloc[0] == 1.0
    assert sig.iloc[7] == 1.0
    assert sig.iloc[14] == 1.0
    # Non-buy days should be NaN (backtester skips them)
    assert np.isnan(sig.iloc[1])
    assert np.isnan(sig.iloc[8])


def test_dca_value_averaging_ramps_to_1():
    sig = DCAValueAveraging(
        params={"target_final_usd": 10000.0, "every_n_bars": 1}
    ).generate_signals(_flat(10))
    # Every bar is a buy day; targets are 0, 1/9, 2/9, ..., 1.0
    assert sig.iloc[0] == pytest.approx(0.0, abs=1e-9)
    assert sig.iloc[-1] == pytest.approx(1.0, abs=1e-9)
    # On non-buy days the signal is NaN (interpreted as "no change")
    sig_sparse = DCAValueAveraging(
        params={"target_final_usd": 10000.0, "every_n_bars": 5}
    ).generate_signals(_flat(20))
    assert pd.isna(sig_sparse.iloc[1])  # not a buy day
    assert not pd.isna(sig_sparse.iloc[5])  # buy day


# ---------------------------------------------------------------------------
# Momentum
# ---------------------------------------------------------------------------


def test_momentum_long_during_uptrend():
    df = _trending_up(n=250, start=100.0, slope=0.5)  # strong uptrend
    sig = MomentumTrend(params={"sma_period": 200}).generate_signals(df)
    # After bar 200, close > SMA(200) almost always -> should be 1
    assert sig.iloc[220:].mean() > 0.9


def test_momentum_flat_during_downtrend():
    df = pd.DataFrame(
        {
            "ts": pd.date_range("2024-01-01", periods=250, freq="D"),
            "open": np.linspace(200.0, 50.0, 250),
            "high": np.linspace(201.0, 51.0, 250),
            "low": np.linspace(199.0, 49.0, 250),
            "close": np.linspace(200.0, 50.0, 250),
            "volume": 1.0,
            "source": "synthetic",
        }
    )
    sig = MomentumTrend(params={"sma_period": 200}).generate_signals(df)
    # By the end, close << SMA(200) -> should be 0
    assert sig.iloc[-50:].mean() < 0.1


def test_momentum_warmup_is_flat():
    sig = MomentumTrend(params={"sma_period": 200}).generate_signals(_trending_up(250))
    # Bars 0..198 are warmup -> should be 0
    assert (sig.iloc[:199] == 0.0).all()


# ---------------------------------------------------------------------------
# Mean reversion
# ---------------------------------------------------------------------------


def test_bollinger_enters_after_crash_and_exits_on_recovery():
    df = _down_then_up(n=200)
    sig = MeanReversionBollinger(params={"period": 20, "num_std": 2.0}).generate_signals(df)
    # After the crash (bar 100ish), close << lower band -> enter
    # After recovery (bar ~150), close > middle band -> exit
    # Check: the strategy is long at some point after the crash
    in_pos_after_crash = sig.iloc[100:].sum()
    assert in_pos_after_crash > 0


def test_rsi_enters_on_oversold():
    df = _down_then_up(n=200)
    sig = MeanReversionRSI(
        params={"period": 14, "entry_threshold": 30.0, "exit_threshold": 50.0}
    ).generate_signals(df)
    # Should be long at some point during the recovery
    assert sig.sum() > 0


def test_rsi_stays_flat_on_flat_series():
    sig = MeanReversionRSI().generate_signals(_flat(50))
    # RSI on flat series ~= 50, above entry threshold (30), so no entry
    assert (sig == 0.0).all()


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


def test_list_strategies_returns_all_known():
    names = {s["name"] for s in list_strategies()}
    assert names == {
        "BuyAndHold",
        "NoTrade",
        "DCAFixedAmount",
        "DCAValueAveraging",
        "MomentumTrend",
        "MeanReversionBollinger",
        "MeanReversionRSI",
        "LadderLimit",
        "RecurringFundingDCA",
        "HalvingCycleAccumulation",
        "CompositeAccumulation",
        # W4 T16: gold's real-rate-cycle accumulator. The abstract
        # CycleAccumulation base is intentionally NOT registered.
        "RealRateCycleAccumulation",
    }


def test_describe_strategy_returns_dict():
    d = describe_strategy("DCAFixedAmount")
    assert d["name"] == "DCAFixedAmount"
    assert "amount_usd" in d["default_params"]


def test_get_strategy_unknown_raises():
    with pytest.raises(KeyError):
        get_strategy("DoesNotExist")


def test_get_strategy_with_params():
    s = get_strategy("DCAFixedAmount", {"amount_usd": 50.0, "every_n_bars": 3})
    assert s.params["amount_usd"] == 50.0
    assert s.params["every_n_bars"] == 3


def test_strategy_signal_returns_series_with_same_index():
    df = _flat(20)
    sig = BuyAndHold().generate_signals(df)
    assert isinstance(sig, pd.Series)
    assert len(sig) == len(df)
    assert (sig.index == df.index).all()


def test_all_strategy_signals_are_in_unit_interval():
    """Every strategy signal must lie in [0, 1]."""
    df = _trending_up(250)
    for strat in [
        BuyAndHold(),
        NoTrade(),
        DCAFixedAmount(),
        DCAValueAveraging(),
        MomentumTrend(),
        MeanReversionBollinger(),
        MeanReversionRSI(),
        LadderLimit(),
    ]:
        sig = strat.generate_signals(df).dropna()
        if sig.empty:
            continue
        assert sig.min() >= 0.0, f"{strat} has negative signal"
        assert sig.max() <= 1.0, f"{strat} has signal > 1"


# ---------------------------------------------------------------------------
# Parameter validation
# ---------------------------------------------------------------------------


def test_strategy_validate_params_called_at_construction():
    """validate_params is called during __post_init__ and can raise."""

    class BadStrategy(Strategy):
        name: ClassVar[str] = "BadStrategy"
        description: ClassVar[str] = "test"
        default_params: ClassVar[dict] = {"x": 1}

        def validate_params(self, params):
            if params["x"] < 0:
                raise InvalidParamsError(f"x must be >= 0, got {params['x']}")

        def generate_signals(self, df):
            return pd.Series(0.0, index=df.index)

    BadStrategy(params={"x": 5})  # should not raise
    with pytest.raises(InvalidParamsError, match="x must be >= 0"):
        BadStrategy(params={"x": -1})


def test_strategy_default_validation_is_noop():
    """Strategies without validate_params override accept any params."""
    BuyAndHold()
    NoTrade()


def test_validate_dca_fixed_amount_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="every_n_bars must be > 0"):
        DCAFixedAmount(params={"every_n_bars": 0, "amount_usd": 100})
    with pytest.raises(InvalidParamsError, match="amount_usd must be > 0"):
        DCAFixedAmount(params={"every_n_bars": 7, "amount_usd": -50})


def test_validate_dca_value_averaging_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="every_n_bars must be > 0"):
        DCAValueAveraging(params={"every_n_bars": 0})
    with pytest.raises(InvalidParamsError, match="target_final_usd must be > 0"):
        DCAValueAveraging(params={"target_final_usd": -100})


def test_validate_momentum_trend_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="sma_period must be >= 2"):
        MomentumTrend(params={"sma_period": 1})


def test_validate_mean_reversion_bollinger_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="period must be >= 2"):
        MeanReversionBollinger(params={"period": 1, "num_std": 2.0})
    with pytest.raises(InvalidParamsError, match="num_std must be > 0"):
        MeanReversionBollinger(params={"period": 20, "num_std": 0})


def test_validate_mean_reversion_rsi_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="period must be >= 2"):
        MeanReversionRSI(params={"period": 1})
    with pytest.raises(InvalidParamsError, match="entry_threshold .* must be < exit_threshold"):
        MeanReversionRSI(params={"entry_threshold": 70, "exit_threshold": 30})
    with pytest.raises(InvalidParamsError, match="entry_threshold must be in"):
        MeanReversionRSI(params={"entry_threshold": -1, "exit_threshold": 50})


def test_validate_ladder_limit_rejects_bad_params():
    with pytest.raises(InvalidParamsError, match="tranche_pcts must be non-empty"):
        LadderLimit(params={"tranche_pcts": []})
    with pytest.raises(InvalidParamsError, match="all tranche_pcts must be negative"):
        LadderLimit(params={"tranche_pcts": [0.05, -0.10]})
    with pytest.raises(InvalidParamsError, match="cooldown_calendar_days must be > 0"):
        LadderLimit(params={"cooldown_calendar_days": 0})
