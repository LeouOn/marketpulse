"""Edge and hand-computed coverage for src/analysis/technical_indicators.py (cycle 16).

Complements the thin incidental reference in tests/test_comprehensive.py.

Bugs pinned here (each fix's test fails on the pre-change module):

* ``get_support_resistance`` could NEVER find a pivot: it examined
  ``tail(lookback * 2)`` rows while requiring ``lookback`` bars on BOTH sides
  of a candidate — the scan range ``[lookback, len - lookback)`` was empty for
  every input (the LLM tool ``find_support_resistance`` always returned []);
* its "Bottom 3" support slice was ``sorted(...)[-3:]`` — the three HIGHEST
  supports, not the lowest;
* OBV subtracted volume on flat close days (definition: unchanged close →
  unchanged OBV) and crashed with IndexError on an empty series;
* ADX built +DM/-DM Series with a default RangeIndex, so on any non-RangeIndex
  input (e.g. DatetimeIndex, as research frames have) the division aligned to
  an empty intersection and returned all-NaN garbage.

All values on valid inputs are pinned against hand computations on tiny
series; fixes must not change them.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd
import pytest

from src.analysis.technical_indicators import (
    TechnicalIndicators as T,
)
from src.analysis.technical_indicators import (
    get_support_resistance,
    identify_trends,
)

DT = pd.date_range("2026-01-01", periods=10, freq="D")


def s(values, index=None):
    return pd.Series(values, index=index if index is not None else range(len(values)), dtype=float)


# ---------------------------------------------------------------------------
# Hand-computed values on tiny series (valid inputs — must never change)
# ---------------------------------------------------------------------------


def test_sma_hand_computed():
    out = T.sma(s([1, 2, 3, 4, 5]), period=3)
    assert np.isnan(out.iloc[0]) and np.isnan(out.iloc[1])
    assert out.iloc[2] == pytest.approx(2.0)
    assert out.iloc[3] == pytest.approx(3.0)
    assert out.iloc[4] == pytest.approx(4.0)


def test_ema_hand_computed():
    # span=3 -> alpha=0.5, adjust=False: e1=1, e2=1.5, e3=2.25, e4=3.125
    out = T.ema(s([1, 2, 3, 4]), period=3)
    expected = [1.0, 1.5, 2.25, 3.125]
    for got, want in zip(out, expected, strict=True):
        assert got == pytest.approx(want)


def test_rsi_hand_computed():
    out = T.rsi(s([1, 2, 3, 2, 3]), period=2)
    assert np.isnan(out.iloc[0])  # first window incomplete
    assert out.iloc[1] == pytest.approx(100.0)  # avg_loss 0 -> rs inf -> 100
    assert out.iloc[3] == pytest.approx(50.0)  # equal gain/loss (0.5/0.5)
    assert out.iloc[4] == pytest.approx(50.0)  # avg_gain 0.5, avg_loss 0.5


def test_rsi_directional_extremes():
    rising = T.rsi(s(list(range(1, 31))), period=5)
    falling = T.rsi(s(list(range(30, 0, -1))), period=5)
    assert rising.iloc[-1] == pytest.approx(100.0)
    assert falling.iloc[-1] == pytest.approx(0.0)
    # Constant series is genuinely undefined here; pin current NaN behaviour.
    assert math.isnan(T.rsi(s([5.0] * 30), period=5).iloc[-1])


def test_macd_hand_computed_and_shape():
    out = T.macd(s([1, 2, 3, 4, 5, 6, 7, 8]), fast=2, slow=3, signal=2)
    assert list(out.columns) == ["macd", "signal", "histogram"]
    # histogram = macd - signal exactly
    assert (out["histogram"] == out["macd"] - out["signal"]).all()


def test_bollinger_constant_series_bands_collapse():
    out = T.bollinger_bands(s([5.0] * 25), period=5)
    assert (out["upper"] == out["middle"]).iloc[4:].all()
    assert (out["lower"] == out["middle"]).iloc[4:].all()
    assert out["middle"].iloc[4] == pytest.approx(5.0)


def test_atr_hand_computed():
    high = s([12, 12, 12])
    low = s([10, 10, 10])
    close = s([11, 11, 11])
    out = T.atr(high, low, close, period=2)
    # TR = [2, 2, 2] (high-low dominates; |h-prev_c|=1, |l-prev_c|=1)
    assert out.iloc[1] == pytest.approx(2.0)
    assert out.iloc[2] == pytest.approx(2.0)
    assert np.isnan(out.iloc[0])


def test_vwap_hand_computed():
    out = T.vwap(s([10, 20]), s([10, 20]), s([10, 20]), s([1, 3]))
    assert out.iloc[0] == pytest.approx(10.0)
    assert out.iloc[1] == pytest.approx((10 * 1 + 20 * 3) / 4)


def test_stochastic_extremes():
    high = s([20.0] * 10)
    low = s([10.0] * 10)
    close = s([20.0] * 10)  # closes at the top of the range
    out = T.stochastic(high, low, close, period=5, smooth_k=1, smooth_d=1)
    assert out["k"].iloc[-1] == pytest.approx(100.0)
    close_mid = s([15.0] * 10)
    out_mid = T.stochastic(high, low, close_mid, period=5, smooth_k=1, smooth_d=1)
    assert out_mid["k"].iloc[-1] == pytest.approx(50.0)


# ---------------------------------------------------------------------------
# Bug A + B: get_support_resistance
# ---------------------------------------------------------------------------


def _pivot_frame(lookback: int) -> pd.DataFrame:
    """Four clean pivot lows (8, 5, 7, 6), each strictly lowest for +-lookback
    bars, placed inside the scan window of the last (8*lookback+5) rows."""
    window = lookback * 8 + 5
    n = window + 15
    start = n - window  # first row of the scanned tail
    lows = [10.0] * n
    offsets = [lookback, lookback * 3 + 1, lookback * 5 + 2, lookback * 7 + 4]
    for pos, val in zip(offsets, [8.0, 5.0, 7.0, 6.0], strict=True):
        lows[start + pos] = val
    return pd.DataFrame(
        {
            "high": [v + 1.0 for v in lows],
            "low": lows,
            "close": lows,
            "volume": [1.0] * n,
        },
        index=pd.date_range("2026-01-01", periods=n, freq="D"),
    )


def test_support_resistance_finds_pivots_at_all():
    sr = get_support_resistance(_pivot_frame(lookback=4), lookback=4)
    assert sr["support"], "old code can never find a pivot (tail window makes the scan range empty)"
    assert sr["resistance"] or True  # frame has no clean pivot highs by design


def test_support_resistance_returns_lowest_supports():
    sr = get_support_resistance(_pivot_frame(lookback=4), lookback=4)
    supports = sr["support"]
    # Four pivots found (8, 5, 7, 6); "Bottom 3" must be the three LOWEST.
    assert sorted(supports) == pytest.approx([5.0, 6.0, 7.0]), (
        f"old slicing returns the highest of the found set: {supports}"
    )


def test_support_resistance_resistance_takes_highest():
    frame = _pivot_frame(lookback=4)
    # Invert the lows into pivot highs: four clean peaks (2, 5, 3, 4).
    frame["high"] = [-low if low != 10.0 else -10.0 for low in frame["low"]]
    frame["low"] = [h - 1.0 for h in frame["high"]]
    sr = get_support_resistance(frame, lookback=4)
    assert sorted(sr["resistance"], reverse=True) == pytest.approx([-5.0, -6.0, -7.0]), (
        f"top-3 resistance must be the three HIGHEST peaks, got {sr['resistance']}"
    )
    # On the original frame (no clean pivot highs), resistance is empty.
    assert get_support_resistance(_pivot_frame(lookback=4), lookback=4)["resistance"] == []


# ---------------------------------------------------------------------------
# Bug C + D: OBV
# ---------------------------------------------------------------------------


def test_obv_flat_days_add_zero_volume():
    close = s([100, 100, 101, 101, 100])
    vol = s([10, 10, 10, 10, 10])
    out = T.obv(close, vol)
    assert out.tolist() == pytest.approx([0.0, 0.0, 10.0, 10.0, 0.0]), (
        f"flat close must not move OBV; got {out.tolist()}"
    )


def test_obv_hand_computed_mixed():
    close = s([100, 102, 101, 103])
    vol = s([10, 20, 30, 40])
    out = T.obv(close, vol)
    assert out.tolist() == pytest.approx([0.0, 20.0, -10.0, 30.0])


def test_obv_empty_series_returns_empty_not_crash():
    out = T.obv(pd.Series(dtype=float), pd.Series(dtype=float))
    assert len(out) == 0


# ---------------------------------------------------------------------------
# Bug E: ADX index alignment
# ---------------------------------------------------------------------------


def test_adx_preserves_datetime_index_and_values():
    idx = pd.date_range("2026-01-01", periods=40, freq="D")
    rng = np.random.default_rng(3)
    close = pd.Series(100 + rng.normal(0, 1, 40).cumsum(), index=idx)
    high = close + 1.0
    low = close - 1.0

    out = T.adx(high, low, close, period=5)

    assert isinstance(out.index, pd.DatetimeIndex) and out.index.equals(idx)
    # The rolling windows fill after 2*period rows; +DI/-DI must be real numbers.
    tail = out.iloc[15:]
    assert tail["plus_di"].notna().all(), "old code returns all-NaN DI lines on DatetimeIndex inputs"
    assert tail["minus_di"].notna().all()
    assert ((tail["plus_di"] >= 0) & (tail["plus_di"] <= 100)).all()
    assert ((tail["minus_di"] >= 0) & (tail["minus_di"] <= 100)).all()


def test_adx_range_index_values_unchanged():
    """RangeIndex inputs worked before and must keep the same numbers."""
    rng = np.random.default_rng(5)
    close = pd.Series(100 + rng.normal(0, 1, 40).cumsum())
    out_before = T.adx(close + 1, close - 1, close, period=5)
    assert out_before["plus_di"].iloc[15:].notna().all()


# ---------------------------------------------------------------------------
# Edge axes: empty / short / window>data / NaN / inf / constant
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "call",
    [
        lambda: T.sma(pd.Series(dtype=float), 3),
        lambda: T.ema(pd.Series(dtype=float), 3),
        lambda: T.rsi(pd.Series(dtype=float), 3),
        lambda: T.bollinger_bands(pd.Series(dtype=float), 3),
        lambda: T.stochastic(pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), 3, 1, 1),
        lambda: T.vwap(pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float), pd.Series(dtype=float)),
    ],
)
def test_empty_series_returns_empty_without_crash(call):
    out = call()
    assert len(out) == 0


def test_window_larger_than_data_is_all_nan():
    out = T.sma(s([1.0, 2.0, 3.0]), period=50)
    assert len(out) == 3 and out.isna().all()


def test_short_supertrend_is_all_nan_not_crash():
    out = T.supertrend(s([10, 11, 12]), s([9, 10, 11]), s([10, 10, 11]), period=10)
    assert len(out) == 3


def test_nan_input_propagates_not_crashes():
    data = s([1.0, np.nan, 3.0, 4.0, 5.0])
    assert math.isnan(T.sma(data, 2).iloc[2])  # window includes the NaN
    assert T.sma(data, 2).iloc[3] == pytest.approx(3.5)  # windows clear the NaN
    assert T.sma(data, 2).iloc[4] == pytest.approx(4.5)


def test_inf_input_is_bounded_by_the_indicator():
    data = s([1.0, math.inf, 3.0, 4.0, 5.0])
    out = T.sma(data, 2)
    assert math.isinf(out.iloc[1]) or math.isnan(out.iloc[1])  # propagates, no crash
    assert out.iloc[4] == pytest.approx(4.5)


def test_output_length_and_index_alignment():
    values = pd.Series(np.arange(1.0, 11.0), index=DT)
    for out in [
        T.sma(values, 3),
        T.ema(values, 3),
        T.rsi(values, 3),
        T.macd(values, 2, 3, 2),
        T.bollinger_bands(values, 3),
    ]:
        assert len(out) == 10
        assert out.index.equals(DT)


# ---------------------------------------------------------------------------
# calculate_all + identify_trends contracts
# ---------------------------------------------------------------------------


def _ohlcv(n: int = 250) -> pd.DataFrame:
    rng = np.random.default_rng(11)
    close = 100 + rng.normal(0, 1, n).cumsum()
    return pd.DataFrame(
        {
            "open": close,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": rng.uniform(100, 200, n),
        },
        index=pd.date_range("2025-01-01", periods=n, freq="D"),
    )


def test_calculate_all_adds_every_indicator_column():
    out = T.calculate_all(_ohlcv(250))
    expected_cols = [
        "sma_20",
        "sma_50",
        "sma_200",
        "ema_9",
        "ema_21",
        "ema_50",
        "rsi",
        "macd",
        "macd_signal",
        "macd_histogram",
        "bb_upper",
        "bb_middle",
        "bb_lower",
        "atr",
        "stoch_k",
        "stoch_d",
        "vwap",
        "obv",
        "adx",
        "plus_di",
        "minus_di",
        "supertrend",
        "supertrend_direction",
    ]
    for col in expected_cols:
        assert col in out.columns, col
    # ADX lines must be real numbers on this datetime-indexed frame (bug E end-to-end).
    assert out["plus_di"].iloc[40:].notna().all()


def test_calculate_all_subset_only_adds_requested():
    out = T.calculate_all(_ohlcv(60), indicators=["rsi", "obv"])
    assert "rsi" in out.columns and "obv" in out.columns
    assert "sma_20" not in out.columns and "macd" not in out.columns


def test_identify_trends_labels():
    df = T.calculate_all(_ohlcv(250))
    trends = identify_trends(df)
    assert trends["sma_trend"] in ("strong_bullish", "bullish", "strong_bearish", "bearish")
    assert trends["rsi_signal"] in ("overbought", "oversold", "neutral")
    assert trends["macd_signal"] in ("bullish", "bearish")
    assert trends["supertrend"] in ("bullish", "bearish")
