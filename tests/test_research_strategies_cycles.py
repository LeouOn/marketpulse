"""Tests for the per-asset cycle accumulation hierarchy (W4/T16).

This is the FIRST of four cycle strategies. It establishes the
``CycleAccumulation`` ABC and the gold-specific ``RealRateCycleAccumulation``
driver (10Y real yield = FRED ``DFII10``).  T17/T18 subclass the same
ABC for equities/oil/housing.

Coverage
--------
1. ``CycleAccumulation`` is abstract (cannot be instantiated directly).
2. ``generate_signals`` with ``factor_df=None`` returns uniform 1.0 (DCA fallback).
3. ``_cycle_phase`` returns 1.5 when real yields fall fast (1Y change < -0.5pp).
4. ``_cycle_phase`` returns 0.3 when real yields rise fast (1Y change > +0.5pp).
5. ``_cycle_phase`` returns 1.0 when real yields change slowly (neutral band).
6. ``_cycle_phase`` returns 1.0 when the factor column is missing (graceful fallback).
7. ``_cycle_phase`` returns 1.0 when there is insufficient history (< lookback/2).
8. ``RealRateCycleAccumulation`` is in ``STRATEGY_REGISTRY``.
9. ``AssetRegistry['GOLD'].cycle_strategy is RealRateCycleAccumulation``.
10. ``generate_signals`` output is clipped to ``[0.0, 1.5]`` for every row.

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T16.
"""

from __future__ import annotations

from typing import Any, ClassVar
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from src.research.strategies import Strategy
from src.research.strategies.cycle_base import CycleAccumulation
from src.research.strategies.RealRateCycleAccumulation import (
    RealRateCycleAccumulation,
)


# ---------------------------------------------------------------------------
# Fixtures / helpers
# ---------------------------------------------------------------------------


def _flat_df(n: int = 10, price: float = 1800.0) -> pd.DataFrame:
    """Flat gold OHLCV DataFrame; price never moves so DCA fallback is stable."""
    return pd.DataFrame(
        {
            "open": price,
            "high": price,
            "low": price,
            "close": price,
            "volume": 1.0,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


def _real_yield_factor_df(
    n: int = 300,
    prior_value: float = 2.5,
    current_value: float | None = None,
    start: str = "2023-01-01",
) -> pd.DataFrame:
    """Macro factor DataFrame with a single ``real_yield_10y`` column.

    All rows are constant at ``prior_value``; if ``current_value`` is given,
    the LAST row is overridden to it.  This guarantees that for any
    ``timestamp`` == last row:

        prior = factor_df["real_yield_10y"].iloc[-lookback] == prior_value
        current = current_value

    so the 1Y change in percentage points is ``current_value - prior_value``
    (T11: DFII10 already in percent, so no scaling).
    """
    values = np.full(n, prior_value, dtype=float)
    if current_value is not None:
        values[-1] = current_value
    return pd.DataFrame(
        {"real_yield_10y": values},
        index=pd.date_range(start, periods=n, freq="D"),
    )


# ---------------------------------------------------------------------------
# Test 1: CycleAccumulation is abstract
# ---------------------------------------------------------------------------


def test_cycle_accumulation_is_abstract() -> None:
    """Direct instantiation must fail because ``_cycle_phase`` is abstract."""
    with pytest.raises(TypeError):
        CycleAccumulation()  # type: ignore[abstract]


# ---------------------------------------------------------------------------
# Test 2: No factor_df -> uniform 1.0 (DCA fallback)
# ---------------------------------------------------------------------------


def test_generate_signals_without_factor_df_returns_uniform_one() -> None:
    """Missing macro data must NOT zero out accumulation (Metis G6 neutral path)."""
    df = _flat_df(n=7)
    strat = RealRateCycleAccumulation()

    out = strat.generate_signals(df)  # factor_df defaults to None

    expected = pd.Series(1.0, index=df.index, name="signal")
    pd.testing.assert_series_equal(out, expected, check_dtype=False)


def test_generate_signals_with_empty_factor_df_returns_uniform_one() -> None:
    """An empty factor_df is treated the same as missing (defensive)."""
    df = _flat_df(n=4)
    strat = RealRateCycleAccumulation()

    out = strat.generate_signals(df, factor_df=pd.DataFrame())

    expected = pd.Series(1.0, index=df.index, name="signal")
    pd.testing.assert_series_equal(out, expected, check_dtype=False)


# ---------------------------------------------------------------------------
# Tests 3-7: RealRateCycleAccumulation phase logic
# ---------------------------------------------------------------------------


class TestRealRateCycle:
    """Phase logic for the 10Y-real-yield-driven gold accumulator.

    Phase thresholds (locked v1 defaults):
        - 1Y change < -0.5pp  -> falling fast  -> intensity 1.5
        - 1Y change > +0.5pp  -> rising fast   -> intensity 0.3
        - otherwise           -> neutral       -> intensity 1.0
    """

    def test_falling_fast_yields_15(self) -> None:
        """1Y drop of 1.0pp (2.5 -> 1.5) is below the -0.5pp threshold -> 1.5."""
        factor_df = _real_yield_factor_df(
            n=300, prior_value=2.5, current_value=1.5
        )
        timestamp = factor_df.index[-1]
        strat = RealRateCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.5)

    def test_rising_fast_yields_03(self) -> None:
        """1Y rise of 1.0pp (1.0 -> 2.0) is above the +0.5pp threshold -> 0.3."""
        factor_df = _real_yield_factor_df(
            n=300, prior_value=1.0, current_value=2.0
        )
        timestamp = factor_df.index[-1]
        strat = RealRateCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(0.3)

    def test_neutral_change_yields_10(self) -> None:
        """1Y drop of 0.2pp (2.0 -> 1.8) is inside the neutral band -> 1.0."""
        factor_df = _real_yield_factor_df(
            n=300, prior_value=2.0, current_value=1.8
        )
        timestamp = factor_df.index[-1]
        strat = RealRateCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_missing_real_yield_column_returns_neutral(self) -> None:
        """A factor_df without ``real_yield_10y`` must fall back to neutral."""
        factor_df = pd.DataFrame(
            {"some_other_macro": [1.0, 2.0, 3.0]},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        timestamp = factor_df.index[-1]
        strat = RealRateCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_insufficient_history_returns_neutral(self) -> None:
        """Less than lookback//2 rows of history -> neutral (can't measure 1Y)."""
        # lookback_days default = 252; lookback//2 = 126. Use only 50 rows.
        factor_df = _real_yield_factor_df(
            n=50, prior_value=2.5, current_value=1.0
        )
        timestamp = factor_df.index[-1]
        strat = RealRateCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test 8: RealRateCycleAccumulation is in STRATEGY_REGISTRY
# ---------------------------------------------------------------------------


def test_real_rate_cycle_is_in_strategy_registry() -> None:
    """The registry (used by T20 ``tools.py``) must expose the strategy by name."""
    from src.research.strategies import _REGISTRY

    assert "RealRateCycleAccumulation" in _REGISTRY
    assert _REGISTRY["RealRateCycleAccumulation"] is RealRateCycleAccumulation


# ---------------------------------------------------------------------------
# Test 9: GOLD AssetConfig.cycle_strategy wiring
# ---------------------------------------------------------------------------


def test_gold_asset_config_wired_to_real_rate_cycle() -> None:
    """AssetRegistry['GOLD'].cycle_strategy must be RealRateCycleAccumulation."""
    from src.research.data import AssetRegistry

    assert AssetRegistry["GOLD"].cycle_strategy is RealRateCycleAccumulation


# ---------------------------------------------------------------------------
# Test 10: generate_signals output is clipped to [0.0, 1.5]
# ---------------------------------------------------------------------------


def test_generate_signals_output_clipped_to_bounds() -> None:
    """Every emitted intensity must lie in [0.0, 1.5] regardless of phase."""
    # Mix of phases: prior 2.5 -> current 1.5 (falling) at the last bar,
    # earlier bars have enough history to also compute a phase.  Whatever
    # the per-row phase is, all outputs must be within bounds.
    factor_df = _real_yield_factor_df(
        n=300, prior_value=2.5, current_value=1.5
    )
    # df covers the last week of the factor window so all timestamps land
    # inside factor_df (sufficient history on every row).
    df = pd.DataFrame(
        {"close": 1800.0, "open": 1800.0, "high": 1800.0, "low": 1800.0, "volume": 1.0},
        index=factor_df.index[-7:],
    )
    strat = RealRateCycleAccumulation()

    out = strat.generate_signals(df, factor_df=factor_df)

    assert isinstance(out, pd.Series)
    assert out.name == "signal"
    assert (out >= 0.0).all(), "signal dipped below 0.0"
    assert (out <= 1.5).all(), "signal exceeded 1.5"
