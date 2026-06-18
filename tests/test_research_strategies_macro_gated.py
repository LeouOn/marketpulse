"""Tests for :class:`MacroGateMixin` (W3/T15).

The mixin scales a host strategy's signal by a per-regime scalar
multiplier.  These tests lock the gate-only contract (Metis SC3):
no cross-asset allocation happens here, only an element-wise scalar
multiply on a single-asset signal.

Coverage
--------
1. All 5 regime multipliers apply correctly.
2. ``regime_tape=None`` is a no-op (returns base signal unchanged).
3. NaN values in ``regime_tape`` fall back to 1.0 (Metis G6).
4. Mixed regime_tape applies per-row multipliers.
5. Output is clipped to ``[0.0, 1.5]`` at both bounds.
6. Composition with ``DCAFixedAmount`` preserves un-gated behaviour.
7. Composition with ``MomentumTrend`` preserves un-gated behaviour.
8. ``regime_multipliers`` defaults to all-1.0 (no-op gate).
9. Accepts both ``Regime`` enum members and their string values.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, ClassVar

import numpy as np
import pandas as pd
import pytest

from src.research.macro.regimes import Regime
from src.research.strategies import (
    BuyAndHold,
    DCAFixedAmount,
    MacroGateMixin,
    MomentumTrend,
    Strategy,
)


# ---------------------------------------------------------------------------
# Test fixtures
# ---------------------------------------------------------------------------


def _flat_df(n: int = 10, price: float = 100.0) -> pd.DataFrame:
    """Flat OHLCV DataFrame; price never moves so signals are deterministic."""
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


def _trending_up_df(n: int = 250, start: float = 100.0) -> pd.DataFrame:
    """Monotonically rising OHLCV; close > SMA(n) after warmup."""
    closes = start + np.arange(n, dtype=float)
    return pd.DataFrame(
        {
            "open": closes,
            "high": closes + 1.0,
            "low": closes - 1.0,
            "close": closes,
            "volume": 1.0,
        },
        index=pd.date_range("2024-01-01", periods=n, freq="D"),
    )


@dataclass
class _ConstantStrategy(Strategy):
    """Stub strategy: emits ``params['value']`` on every bar.

    Lets tests isolate the mixin's multiplier math from any real
    indicator logic.
    """

    name: ClassVar[str] = "_ConstantStrategy"
    description: ClassVar[str] = "Test stub: constant signal."
    default_params: ClassVar[dict[str, Any]] = {"value": 1.0}

    def generate_signals(self, df: pd.DataFrame) -> pd.Series:
        return pd.Series(float(self.params["value"]), index=df.index)


class _GatedConstant(MacroGateMixin, _ConstantStrategy):
    """MacroGateMixin composed with the constant-signal stub."""


class _GatedDCA(MacroGateMixin, DCAFixedAmount):
    """MacroGateMixin composed with DCAFixedAmount."""


class _GatedMomentum(MacroGateMixin, MomentumTrend):
    """MacroGateMixin composed with MomentumTrend."""


# Distinct multiplier per regime, chosen so each is identifiable in
# the output signal after multiplying a unit base.
DISTINCT_MULTIPLIERS: dict[Regime, float] = {
    Regime.RISK_ON: 0.5,
    Regime.DEFLATION_SCARE: 0.7,
    Regime.INFLATION_ACCEL: 0.9,
    Regime.REAL_YIELD_SHOCK: 1.1,
    Regime.RECESSION: 1.5,
}


def _set_multipliers(inst: MacroGateMixin, mult: dict[Regime, float]) -> MacroGateMixin:
    """Shadow the class-level regime_multipliers on an instance."""
    inst.regime_multipliers = dict(mult)
    return inst


# ---------------------------------------------------------------------------
# Test 1: All 5 regime multipliers apply correctly
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("regime,expected", list(DISTINCT_MULTIPLIERS.items()))
def test_each_regime_multiplier_applies(regime: Regime, expected: float) -> None:
    """Base signal of 1.0 * multiplier should equal the multiplier (no clip)."""
    df = _flat_df(n=5)
    gated = _set_multipliers(_GatedConstant(), DISTINCT_MULTIPLIERS)
    tape = pd.Series([regime] * len(df), index=df.index)

    out = gated.generate_signals_gated(df, tape)

    pd.testing.assert_series_equal(
        out,
        pd.Series([expected] * len(df), index=df.index, dtype=float),
        check_names=False,
    )


# ---------------------------------------------------------------------------
# Test 2: None regime_tape is a no-op
# ---------------------------------------------------------------------------


def test_none_regime_tape_returns_base_signal_unchanged() -> None:
    """When regime_tape is None, gate is bypassed (Metis G6 neutral path)."""
    df = _flat_df(n=8)
    gated = _set_multipliers(_GatedConstant(params={"value": 0.3}), DISTINCT_MULTIPLIERS)

    base = gated.generate_signals(df)
    out = gated.generate_signals_gated(df, None)

    pd.testing.assert_series_equal(out, base, check_names=False)


# ---------------------------------------------------------------------------
# Test 3: NaN values in regime_tape fall back to 1.0 (Metis G6)
# ---------------------------------------------------------------------------


def test_nan_regime_tape_values_treated_as_neutral() -> None:
    """NaN regimes (FRED outage / warmup gap) -> multiplier 1.0."""
    df = _flat_df(n=6)
    gated = _set_multipliers(_GatedConstant(params={"value": 1.0}), DISTINCT_MULTIPLIERS)
    # Tape with NaN in some rows; remainder RISK_ON (mult 0.5).
    tape = pd.Series(
        [Regime.RISK_ON, np.nan, Regime.RISK_ON, np.nan, np.nan, Regime.RISK_ON],
        index=df.index,
    )

    out = gated.generate_signals_gated(df, tape)

    expected_values = [0.5, 1.0, 0.5, 1.0, 1.0, 0.5]  # NaN -> 1.0
    pd.testing.assert_series_equal(
        out,
        pd.Series(expected_values, index=df.index, dtype=float),
        check_names=False,
    )


# ---------------------------------------------------------------------------
# Test 4: Mixed regime_tape applies per-row multipliers
# ---------------------------------------------------------------------------


def test_mixed_regime_tape_applies_per_row() -> None:
    """A tape that switches regime day-to-day gates each row independently."""
    df = _flat_df(n=5)
    gated = _set_multipliers(_GatedConstant(params={"value": 1.0}), DISTINCT_MULTIPLIERS)
    tape = pd.Series(
        [
            Regime.RISK_ON,          # 0.5
            Regime.DEFLATION_SCARE,  # 0.7
            Regime.INFLATION_ACCEL,  # 0.9
            Regime.REAL_YIELD_SHOCK, # 1.1
            Regime.RECESSION,        # 1.5
        ],
        index=df.index,
    )

    out = gated.generate_signals_gated(df, tape)

    expected = pd.Series([0.5, 0.7, 0.9, 1.1, 1.5], index=df.index, dtype=float)
    pd.testing.assert_series_equal(out, expected, check_names=False)


# ---------------------------------------------------------------------------
# Test 5: Clipping to [0.0, 1.5]
# ---------------------------------------------------------------------------


def test_output_clipped_to_bounds() -> None:
    """Multiplier * base must stay within [0.0, 1.5] even with extreme values."""
    df = _flat_df(n=4)
    gated = _GatedConstant(params={"value": 1.0})
    # Contrived multipliers: one above the upper clip, one negative (lower clip).
    gated.regime_multipliers = {
        Regime.RISK_ON: 2.5,      # 1.0 * 2.5 = 2.5 -> clipped to 1.5
        Regime.RECESSION: -0.5,   # 1.0 * -0.5 = -0.5 -> clipped to 0.0
        Regime.DEFLATION_SCARE: 1.5,  # exactly at upper bound, no clip
        Regime.INFLATION_ACCEL: 0.0,  # exactly at lower bound, no clip
    }
    tape = pd.Series(
        [
            Regime.RISK_ON,
            Regime.RECESSION,
            Regime.DEFLATION_SCARE,
            Regime.INFLATION_ACCEL,
        ],
        index=df.index,
    )

    out = gated.generate_signals_gated(df, tape)

    expected = pd.Series([1.5, 0.0, 1.5, 0.0], index=df.index, dtype=float)
    pd.testing.assert_series_equal(out, expected, check_names=False)
    assert (out >= 0.0).all(), "gated signal dipped below 0.0"
    assert (out <= 1.5).all(), "gated signal exceeded 1.5"


# ---------------------------------------------------------------------------
# Test 6: Composition with DCAFixedAmount preserves base behaviour
# ---------------------------------------------------------------------------


def test_compose_with_dca_preserves_base_behaviour() -> None:
    """GatedDCA.generate_signals (un-gated) must equal DCAFixedAmount."""
    df = _flat_df(n=20)
    plain = DCAFixedAmount(params={"every_n_bars": 5, "amount_usd": 50.0})
    gated = _GatedDCA(params={"every_n_bars": 5, "amount_usd": 50.0})
    _set_multipliers(gated, DISTINCT_MULTIPLIERS)

    base_plain = plain.generate_signals(df)
    base_gated = gated.generate_signals(df)

    pd.testing.assert_series_equal(base_gated, base_plain, check_names=False)

    # And the gated path actually attenuates the buy-day signals.
    tape = pd.Series([Regime.RISK_ON] * len(df), index=df.index)  # mult 0.5
    gated_out = gated.generate_signals_gated(df, tape)

    buy_mask = base_plain == 1.0
    # On buy days, gated = 1.0 * 0.5 = 0.5; on non-buy days, NaN * 0.5 = NaN.
    assert np.allclose(gated_out[buy_mask].to_numpy(), 0.5, equal_nan=True)
    assert gated_out[~buy_mask].isna().all()


# ---------------------------------------------------------------------------
# Test 7: Composition with MomentumTrend preserves base behaviour
# ---------------------------------------------------------------------------


def test_compose_with_momentum_preserves_base_behaviour() -> None:
    """GatedMomentum.generate_signals (un-gated) must equal MomentumTrend."""
    df = _trending_up_df(n=250)
    plain = MomentumTrend(params={"sma_period": 200})
    gated = _GatedMomentum(params={"sma_period": 200})
    _set_multipliers(gated, DISTINCT_MULTIPLIERS)

    base_plain = plain.generate_signals(df)
    base_gated = gated.generate_signals(df)

    pd.testing.assert_series_equal(base_gated, base_plain, check_names=False)

    # With RISK_ON tape (mult 0.5), the post-warmup long signals halve.
    tape = pd.Series([Regime.RISK_ON] * len(df), index=df.index)
    gated_out = gated.generate_signals_gated(df, tape)

    long_mask = base_plain == 1.0
    flat_mask = base_plain == 0.0
    # Long rows: 1.0 * 0.5 = 0.5. Flat rows: 0.0 * 0.5 = 0.0.
    assert np.allclose(gated_out[long_mask].to_numpy(), 0.5)
    assert np.allclose(gated_out[flat_mask].to_numpy(), 0.0)


# ---------------------------------------------------------------------------
# Test 8: regime_multipliers defaults to all-1.0 (no-op gate)
# ---------------------------------------------------------------------------


def test_default_regime_multipliers_are_noop() -> None:
    """Without overriding regime_multipliers, the gate is a no-op."""
    df = _flat_df(n=5)
    gated = _GatedConstant()  # no override

    # Sanity: every regime maps to 1.0 by default.
    for regime in Regime:
        assert gated.regime_multipliers[regime] == 1.0

    # All-five-regime tape still produces base signal unchanged.
    tape = pd.Series(list(Regime), index=df.index)
    base = gated.generate_signals(df)
    out = gated.generate_signals_gated(df, tape)

    pd.testing.assert_series_equal(out, base, check_names=False)


# ---------------------------------------------------------------------------
# Test 9: Accepts Regime enum OR string values (T12 interop)
# ---------------------------------------------------------------------------


def test_regime_tape_accepts_string_or_enum_values() -> None:
    """T12's classifier emits string column names; mixin must accept both."""
    df = _flat_df(n=5)
    gated = _set_multipliers(_GatedConstant(params={"value": 1.0}), DISTINCT_MULTIPLIERS)

    regime_order = [
        Regime.RISK_ON,
        Regime.DEFLATION_SCARE,
        Regime.INFLATION_ACCEL,
        Regime.REAL_YIELD_SHOCK,
        Regime.RECESSION,
    ]
    enum_tape = pd.Series(regime_order, index=df.index)
    # pandas flattens str-Enum values to plain str on Series construction,
    # so the "string" tape is built explicitly from ``.value``.
    string_tape = pd.Series([r.value for r in regime_order], index=df.index)

    out_enum = gated.generate_signals_gated(df, enum_tape)
    out_str = gated.generate_signals_gated(df, string_tape)

    # Both encodings produce identical gating.
    pd.testing.assert_series_equal(out_enum, out_str, check_names=False)

    # And the gating actually happened (not all 1.0).
    assert not np.allclose(out_enum.to_numpy(), 1.0)


def test_unknown_regime_string_falls_back_to_neutral() -> None:
    """A garbage regime label must not zero out the strategy (defensive)."""
    df = _flat_df(n=3)
    gated = _set_multipliers(_GatedConstant(params={"value": 1.0}), DISTINCT_MULTIPLIERS)
    tape = pd.Series(["BOGUS_REGIME", "RISK_ON", "ALSO_BOGUS"], index=df.index)

    out = gated.generate_signals_gated(df, tape)

    # Bogus rows -> 1.0 (neutral); RISK_ON row -> 0.5.
    expected = pd.Series([1.0, 0.5, 1.0], index=df.index, dtype=float)
    pd.testing.assert_series_equal(out, expected, check_names=False)
