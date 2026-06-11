"""Tests for RecurringFundingDCA strategy.

Covers: default params, signal generation, validation, registry inclusion,
and integration with the backtest engine's inflows parameter.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from src.research.backtest import run_backtest
from src.research.scaling import FixedDollar
from src.research.strategies import (
    InvalidParamsError,
    RecurringFundingDCA,
    list_strategies,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _flat(n: int = 100, price: float = 50_000.0) -> pd.DataFrame:
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


# ---------------------------------------------------------------------------
# Unit tests
# ---------------------------------------------------------------------------


def test_default_params():
    """Default params have every_n_bars=30 and validation passes."""
    s = RecurringFundingDCA()
    assert s.params["every_n_bars"] == 30


def test_signals_only_on_buy_days():
    """Signal is 1.0 every 30 bars, NaN elsewhere."""
    df = _flat(90)
    sig = RecurringFundingDCA(params={"every_n_bars": 30}).generate_signals(df)

    # Buy days: 0, 30, 60
    assert sig.iloc[0] == 1.0
    assert sig.iloc[30] == 1.0
    assert sig.iloc[60] == 1.0

    # Non-buy days are NaN
    assert np.isnan(sig.iloc[1])
    assert np.isnan(sig.iloc[15])
    assert np.isnan(sig.iloc[89])

    # Exactly 3 buy days in 90 bars
    buy_days = sig.dropna()
    assert len(buy_days) == 3
    assert (buy_days == 1.0).all()


def test_validate_rejects_zero_every_n():
    """every_n_bars=0 must raise InvalidParamsError."""
    with pytest.raises(InvalidParamsError, match="every_n_bars must be > 0"):
        RecurringFundingDCA(params={"every_n_bars": 0})


def test_registry_includes():
    """RecurringFundingDCA appears in list_strategies()."""
    names = {s["name"] for s in list_strategies()}
    assert "RecurringFundingDCA" in names


# ---------------------------------------------------------------------------
# Integration tests (pair with inflows + FixedDollar scaling)
# ---------------------------------------------------------------------------


def test_paired_with_inflows_buys():
    """End-to-end: RecurringFundingDCA + inflows produces actual buys."""
    df = _flat(90, price=50_000.0)
    result = run_backtest(
        df,
        strategy=RecurringFundingDCA(params={"every_n_bars": 30}),
        scaling=FixedDollar(params={"amount_usd": 500.0}),
        starting_equity=0.0,
        inflows=[{"every_n_bars": 30, "amount_usd": 500.0}],
    )
    # Should have 3 deposits (bars 0, 30, 60) and 3 buys
    assert len(result.deposits) > 0
    buys = [t for t in result.trades if t.side == "buy"]
    assert len(buys) > 0
    assert result.metrics["total_deposited"] > 0


def test_paired_with_inflows_works_with_zero_starting_equity():
    """Starting from $0, the entire portfolio comes from deposits."""
    df = _flat(90, price=50_000.0)
    result = run_backtest(
        df,
        strategy=RecurringFundingDCA(params={"every_n_bars": 30}),
        scaling=FixedDollar(params={"amount_usd": 500.0}),
        starting_equity=0.0,
        inflows=[{"every_n_bars": 30, "amount_usd": 500.0}],
    )
    # Total deposited should equal 3 deposits * $500
    expected_deposits = 3 * 500.0
    assert result.metrics["total_deposited"] == pytest.approx(
        expected_deposits, abs=1.0
    )
    # Ending equity should be > 0 (we bought BTC with the deposits)
    assert result.ending_equity > 0
