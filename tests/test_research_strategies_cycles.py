"""Tests for the per-asset cycle accumulation hierarchy (W4/T16-T17).

This covers the ``CycleAccumulation`` ABC and three concrete subclasses:
    - ``RealRateCycleAccumulation``   (T16, gold,    DFII10 driver)
    - ``EarningsCycleAccumulation``   (T17, equities, Sahm-recession driver)
    - ``OPECCycleAccumulation``       (T17, oil,     EIA inventory driver)

T18 will add ``MortgageCycleAccumulation`` for housing (separate file).

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

T17 additions (EarningsCycleAccumulation, OPECCycleAccumulation):
11. Earnings: Sahm recession == True  -> 1.5 (buy fear).
12. Earnings: Sahm recession == False -> 0.7 (normal accumulation; CAPE stubbed v1).
13. Earnings: missing sahm_recession column -> graceful fallback.
14. Earnings: in STRATEGY_REGISTRY + AssetRegistry['EQUITIES'] wiring.
15. OPEC: drawing inventories (z < -1, spot up) -> 1.0.
16. OPEC: building inventories (z > 1)         -> 0.3.
17. OPEC: missing oil_inventories_z column     -> 1.0 (neutral fallback).
18. OPEC: in STRATEGY_REGISTRY + AssetRegistry['OIL'] wiring.

Spec: .omo/plans/multi-asset-macro-research-lab.md W4 T16-T17.
"""

from __future__ import annotations

from typing import Any, ClassVar
from dataclasses import dataclass

import numpy as np
import pandas as pd
import pytest

from src.research.strategies import Strategy
from src.research.strategies.cycle_base import CycleAccumulation
from src.research.strategies.EarningsCycleAccumulation import (
    EarningsCycleAccumulation,
)
from src.research.strategies.OPECCycleAccumulation import (
    OPECCycleAccumulation,
)
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


# ===========================================================================
# T17: EarningsCycleAccumulation (equities, Sahm-recession driver)
# ===========================================================================


def _sahm_factor_df(
    n: int = 10,
    recession_at_last: bool = False,
    start: str = "2024-01-01",
) -> pd.DataFrame:
    """Macro factor DataFrame with a boolean ``sahm_recession`` column.

    All rows are False except optionally the LAST row, which can be set
    to ``recession_at_last=True`` to simulate a Sahm-rule trigger at the
    bar under test.
    """
    flags = np.zeros(n, dtype=bool)
    if recession_at_last:
        flags[-1] = True
    return pd.DataFrame(
        {"sahm_recession": flags},
        index=pd.date_range(start, periods=n, freq="D"),
    )


class TestEarningsCycle:
    """Phase logic for the Sahm-recession-driven equity accumulator.

    Phase thresholds (locked v1 defaults):
        - sahm_recession == True   -> recession       -> 1.5
        - sahm_recession == False  -> normal          -> 0.7
        (CAPE mania branch is stubbed for v1 -- unreachable today.)
    """

    def test_recession_yields_15(self) -> None:
        """Sahm recession trigger at the timestamp -> intensity 1.5 (buy fear)."""
        factor_df = _sahm_factor_df(n=10, recession_at_last=True)
        timestamp = factor_df.index[-1]
        strat = EarningsCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.5)

    def test_expansion_yields_07(self) -> None:
        """No recession (sahm_recession=False, CAPE stubbed) -> intensity 0.7."""
        factor_df = _sahm_factor_df(n=10, recession_at_last=False)
        timestamp = factor_df.index[-1]
        strat = EarningsCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(0.7)

    def test_missing_sahm_column_returns_normal(self) -> None:
        """A factor_df without ``sahm_recession`` falls back to normal (0.7)."""
        factor_df = pd.DataFrame(
            {"some_other_macro": [1.0, 2.0, 3.0]},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        timestamp = factor_df.index[-1]
        strat = EarningsCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(0.7)

    def test_in_strategy_registry(self) -> None:
        """The registry (used by T20 ``tools.py``) must expose the strategy by name."""
        from src.research.strategies import _REGISTRY

        assert "EarningsCycleAccumulation" in _REGISTRY
        assert _REGISTRY["EarningsCycleAccumulation"] is EarningsCycleAccumulation

    def test_equities_asset_config_wired(self) -> None:
        """AssetRegistry['EQUITIES'].cycle_strategy must be EarningsCycleAccumulation."""
        from src.research.data import AssetRegistry

        assert AssetRegistry["EQUITIES"].cycle_strategy is EarningsCycleAccumulation


# ===========================================================================
# T17: OPECCycleAccumulation (oil, EIA inventory driver)
# ===========================================================================


def _oil_inventory_factor_df(
    n: int = 10,
    inventory_z_last: float = 0.0,
    spot_trend_last: float = 0.0,
    start: str = "2024-01-01",
) -> pd.DataFrame:
    """Macro factor DataFrame with ``oil_inventories_z`` + ``oil_spot_trend``.

    All rows are zero (neutral); the LAST row is overridden to the given
    values so the timestamp under test sees a clean phase trigger.
    """
    inv = np.zeros(n, dtype=float)
    spot = np.zeros(n, dtype=float)
    inv[-1] = inventory_z_last
    spot[-1] = spot_trend_last
    return pd.DataFrame(
        {"oil_inventories_z": inv, "oil_spot_trend": spot},
        index=pd.date_range(start, periods=n, freq="D"),
    )


class TestOPECCycle:
    """Phase logic for the EIA-inventory-driven oil accumulator.

    Phase thresholds (locked v1 defaults):
        - inventory_z < -1.0 AND spot_trend > 0  -> drawing  -> 1.0
        - inventory_z > +1.0                      -> building -> 0.3
        - otherwise                               -> neutral  -> 1.0
    """

    def test_drawing_inventories_yields_10(self) -> None:
        """inventory_z = -2.0 (drawing) AND spot_trend = +1.0 -> 1.0 (trend-follow)."""
        factor_df = _oil_inventory_factor_df(
            n=10, inventory_z_last=-2.0, spot_trend_last=1.0
        )
        timestamp = factor_df.index[-1]
        strat = OPECCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_building_inventories_yields_03(self) -> None:
        """inventory_z = +2.0 (building) -> 0.3 (slow accumulation, bearish)."""
        factor_df = _oil_inventory_factor_df(
            n=10, inventory_z_last=2.0, spot_trend_last=0.0
        )
        timestamp = factor_df.index[-1]
        strat = OPECCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(0.3)

    def test_neutral_inventories_yields_10(self) -> None:
        """inventory_z = 0.0 (neutral band) -> 1.0."""
        factor_df = _oil_inventory_factor_df(
            n=10, inventory_z_last=0.0, spot_trend_last=0.0
        )
        timestamp = factor_df.index[-1]
        strat = OPECCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_drawing_without_spot_trend_falls_to_neutral(self) -> None:
        """inventory_z = -2.0 but spot_trend = 0.0 (no confirmation) -> neutral 1.0.

        The draw branch requires BOTH inventory draw AND spot price
        confirmation.  Without confirmation we fall through to neutral
        (conservative: don't lean in without price action).
        """
        factor_df = _oil_inventory_factor_df(
            n=10, inventory_z_last=-2.0, spot_trend_last=0.0
        )
        timestamp = factor_df.index[-1]
        strat = OPECCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_missing_inventory_column_returns_neutral(self) -> None:
        """A factor_df without ``oil_inventories_z`` falls back to neutral (1.0).

        This is the common case on T11's v1 factor set (EIA inventories
        not yet wired).  We must NOT raise -- the strategy continues at
        the standard DCA cadence.
        """
        # Reset the once-per-process warning flag so this test is
        # deterministic regardless of execution order.
        OPECCycleAccumulation._missing_col_warned = False

        factor_df = pd.DataFrame(
            {"some_other_macro": [1.0, 2.0, 3.0]},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        timestamp = factor_df.index[-1]
        strat = OPECCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_in_strategy_registry(self) -> None:
        """The registry (used by T20 ``tools.py``) must expose the strategy by name."""
        from src.research.strategies import _REGISTRY

        assert "OPECCycleAccumulation" in _REGISTRY
        assert _REGISTRY["OPECCycleAccumulation"] is OPECCycleAccumulation

    def test_oil_asset_config_wired(self) -> None:
        """AssetRegistry['OIL'].cycle_strategy must be OPECCycleAccumulation."""
        from src.research.data import AssetRegistry

        assert AssetRegistry["OIL"].cycle_strategy is OPECCycleAccumulation


# ---------------------------------------------------------------------------
# W4 T18: MortgageCycleAccumulation (housing cycle strategy)
#
# Driver: ``mortgage_30y`` (FRED ``MORTGAGE30US`` -- 30Y fixed mortgage
# rate, weekly cadence forward-filled to daily by T11's MacroFactorProvider).
# Values are in PERCENT (7.0 means 7.0%), so the 1Y change in percentage
# points is the raw difference (T11 finding).
#
# Economic rationale (Metis SC5):
#     Falling mortgage rates improve housing affordability and open refi
#     windows -- we accumulate FASTER (1.5x).  Rising mortgage rates
#     squeeze affordability and cool demand -- we accumulate SLOWER (0.3x).
#     In the neutral band we accumulate at the standard 1.0x DCA cadence.
#
# The strategy also exposes a ``_create_mortgage`` helper that wraps
# ``FixedRateLoan`` as an *interest-only proxy* for a 30Y amortizing
# mortgage (Metis SC5 documented simplification).
# ---------------------------------------------------------------------------


def _mortgage_factor_df(
    n: int = 300,
    prior_value: float = 7.0,
    current_value: float | None = None,
    start: str = "2023-01-01",
) -> pd.DataFrame:
    """Macro factor DataFrame with a single ``mortgage_30y`` column.

    All rows are constant at ``prior_value``; if ``current_value`` is
    given, the LAST row is overridden to it.  This guarantees that for
    the last timestamp:

        prior = factor_df["mortgage_30y"].iloc[-lookback] == prior_value
        current = current_value

    so the 1Y change in percentage points is ``current_value - prior_value``
    (T11: MORTGAGE30US already in percent, no scaling).
    """
    values = np.full(n, prior_value, dtype=float)
    if current_value is not None:
        values[-1] = current_value
    return pd.DataFrame(
        {"mortgage_30y": values},
        index=pd.date_range(start, periods=n, freq="D"),
    )


class TestMortgageCycle:
    """Phase logic for the 30Y-mortgage-rate-driven housing accumulator.

    Phase thresholds (locked v1 defaults):
        - 1Y change < -0.5pp  -> falling fast  -> intensity 1.5
        - 1Y change > +0.5pp  -> rising fast   -> intensity 0.3
        - otherwise           -> neutral       -> intensity 1.0
    """

    def test_falling_mortgage_rate_yields_15(self) -> None:
        """1Y drop of 1.0pp (7.0 -> 6.0) is below the -0.5pp threshold -> 1.5."""
        from src.research.strategies.MortgageCycleAccumulation import (
            MortgageCycleAccumulation,
        )

        factor_df = _mortgage_factor_df(
            n=300, prior_value=7.0, current_value=6.0
        )
        timestamp = factor_df.index[-1]
        strat = MortgageCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.5)

    def test_rising_mortgage_rate_yields_03(self) -> None:
        """1Y rise of 1.0pp (6.0 -> 7.0) is above the +0.5pp threshold -> 0.3."""
        from src.research.strategies.MortgageCycleAccumulation import (
            MortgageCycleAccumulation,
        )

        factor_df = _mortgage_factor_df(
            n=300, prior_value=6.0, current_value=7.0
        )
        timestamp = factor_df.index[-1]
        strat = MortgageCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(0.3)

    def test_neutral_mortgage_rate_yields_10(self) -> None:
        """1Y drop of 0.2pp (7.0 -> 6.8) is inside the neutral band -> 1.0."""
        from src.research.strategies.MortgageCycleAccumulation import (
            MortgageCycleAccumulation,
        )

        factor_df = _mortgage_factor_df(
            n=300, prior_value=7.0, current_value=6.8
        )
        timestamp = factor_df.index[-1]
        strat = MortgageCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_missing_mortgage_30y_column_returns_neutral(self) -> None:
        """A factor_df without ``mortgage_30y`` must fall back to neutral."""
        from src.research.strategies.MortgageCycleAccumulation import (
            MortgageCycleAccumulation,
        )

        factor_df = pd.DataFrame(
            {"some_other_macro": [1.0, 2.0, 3.0]},
            index=pd.date_range("2024-01-01", periods=3, freq="D"),
        )
        timestamp = factor_df.index[-1]
        strat = MortgageCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)

    def test_insufficient_history_returns_neutral(self) -> None:
        """Less than lookback//2 rows of history -> neutral (can't measure 1Y)."""
        from src.research.strategies.MortgageCycleAccumulation import (
            MortgageCycleAccumulation,
        )

        # lookback_days default = 252; lookback//2 = 126. Use only 50 rows.
        factor_df = _mortgage_factor_df(
            n=50, prior_value=7.0, current_value=5.0
        )
        timestamp = factor_df.index[-1]
        strat = MortgageCycleAccumulation()

        intensity = strat._cycle_phase(timestamp, factor_df)

        assert intensity == pytest.approx(1.0)


# ---------------------------------------------------------------------------
# Test: MortgageCycleAccumulation is in STRATEGY_REGISTRY
# ---------------------------------------------------------------------------


def test_mortgage_cycle_is_in_strategy_registry() -> None:
    """The registry (used by T20 ``tools.py``) must expose the strategy by name."""
    from src.research.strategies import _REGISTRY
    from src.research.strategies.MortgageCycleAccumulation import (
        MortgageCycleAccumulation,
    )

    assert "MortgageCycleAccumulation" in _REGISTRY
    assert _REGISTRY["MortgageCycleAccumulation"] is MortgageCycleAccumulation


# ---------------------------------------------------------------------------
# Test: HOUSING AssetConfig.cycle_strategy wiring
# ---------------------------------------------------------------------------


def test_housing_asset_config_wired_to_mortgage_cycle() -> None:
    """AssetRegistry['HOUSING'].cycle_strategy must be MortgageCycleAccumulation."""
    from src.research.data import AssetRegistry
    from src.research.strategies.MortgageCycleAccumulation import (
        MortgageCycleAccumulation,
    )

    assert AssetRegistry["HOUSING"].cycle_strategy is MortgageCycleAccumulation


# ---------------------------------------------------------------------------
# Test: Metis SC5 mandatory documentation -- "interest-only proxy" docstring
# ---------------------------------------------------------------------------


def test_mortgage_cycle_docstring_contains_interest_only_proxy() -> None:
    """Metis SC5: class docstring MUST explicitly document the simplification."""
    from src.research.strategies.MortgageCycleAccumulation import (
        MortgageCycleAccumulation,
    )

    assert MortgageCycleAccumulation.__doc__ is not None
    assert "interest-only proxy" in MortgageCycleAccumulation.__doc__, (
        "Metis SC5 mandatory: MortgageCycleAccumulation.__doc__ must "
        "contain the literal string 'interest-only proxy' to document "
        "the FixedRateLoan simplification."
    )
