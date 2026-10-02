"""Offline tests for ``src/analysis/order_flow.py``.

Deterministic synthetic bars/candles only -- no live data, no network.
Extends the partial ImbalanceDetector coverage that lives in
tests/test_undefined_name_fixes.py (that file is not modified).
"""

from __future__ import annotations

from datetime import datetime, timedelta

import numpy as np
import pandas as pd
import pytest

from src.analysis.order_flow import (
    AbsorptionDetector,
    CumulativeVolumeDeltaCalculator,
    Imbalance,
    ImbalanceDetector,
    VolumeBar,
    VolumeDeltaAnalyzer,
    VolumeProfile,
    VolumeProfileBuilder,
)

T0 = datetime(2026, 1, 5, 9, 30)


def _candles(rows, start=T0, freq="1min") -> pd.DataFrame:
    """rows: list of (open, high, low, close, volume)."""
    idx = pd.date_range(start, periods=len(rows), freq=freq)
    return pd.DataFrame(
        {
            "open": [r[0] for r in rows],
            "high": [r[1] for r in rows],
            "low": [r[2] for r in rows],
            "close": [r[3] for r in rows],
            "volume": [float(r[4]) for r in rows],
        },
        index=idx,
    )


def _bars(deltas, start=T0) -> list[VolumeBar]:
    """Bars with total volume 100 and the given buy-sell delta."""
    bars = []
    for i, d in enumerate(deltas):
        buy = (100.0 + d) / 2
        sell = (100.0 - d) / 2
        bars.append(
            VolumeBar(
                timestamp=start + timedelta(minutes=i),
                buy_volume=buy,
                sell_volume=sell,
                total_volume=100.0,
                delta=float(d),
                delta_percent=d,
            )
        )
    return bars


# ---------------------------------------------------------------------------
# VolumeBar.from_trades
# ---------------------------------------------------------------------------


def test_volume_bar_from_trades_splits_buy_and_sell():
    trades = [
        {"side": "buy", "volume": 30},
        {"side": "sell", "volume": 10},
        {"side": "buy", "volume": 20},
    ]

    bar = VolumeBar.from_trades(T0, trades)

    assert bar.buy_volume == 50
    assert bar.sell_volume == 10
    assert bar.total_volume == 60
    assert bar.delta == 40
    assert bar.delta_percent == pytest.approx(40 / 60 * 100)


def test_volume_bar_from_empty_trades_is_zeroed():
    bar = VolumeBar.from_trades(T0, [])

    assert bar.total_volume == 0
    assert bar.delta == 0
    assert bar.delta_percent == 0  # guarded, no ZeroDivisionError


# ---------------------------------------------------------------------------
# CumulativeVolumeDeltaCalculator
# ---------------------------------------------------------------------------


def test_calculate_cvd_cumulates_deltas_over_timestamps():
    cvd = CumulativeVolumeDeltaCalculator().calculate_cvd(_bars([10, -5, 20]))

    assert list(cvd.index) == [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]
    assert cvd.iloc[0] == 10
    assert cvd.iloc[1] == 5
    assert cvd.iloc[2] == 25


def test_calculate_cvd_empty_bars_returns_empty_series():
    cvd = CumulativeVolumeDeltaCalculator().calculate_cvd([])

    assert isinstance(cvd, pd.Series)
    assert cvd.empty


def test_update_cvd_tracks_running_total_and_history():
    calc = CumulativeVolumeDeltaCalculator()

    assert calc.update_cvd(_bars([10])[0]) == 10
    assert calc.update_cvd(_bars([0], start=T0 + timedelta(minutes=1))[0]) == 10
    assert calc.update_cvd(_bars([-4], start=T0 + timedelta(minutes=2))[0]) == 6

    assert [ts for ts, _ in calc.cvd_history] == [T0, T0 + timedelta(minutes=1), T0 + timedelta(minutes=2)]
    assert [v for _, v in calc.cvd_history] == [10, 10, 6]


def test_cvd_slope_sign_and_short_history():
    calc = CumulativeVolumeDeltaCalculator()
    for bar in _bars([1, 2, 3, 4, 5, 6, 7, 8, 9, 10]):
        calc.update_cvd(bar)
    assert calc.get_cvd_slope() > 0

    calc2 = CumulativeVolumeDeltaCalculator()
    # The slope is over the RUNNING cvd, so negative deltas make it decrease.
    for bar in _bars([-10, -9, -8, -7, -6, -5, -4, -3, -2, -1]):
        calc2.update_cvd(bar)
    assert calc2.get_cvd_slope() < 0

    # Not enough history -> flat 0.0 by contract.
    calc3 = CumulativeVolumeDeltaCalculator()
    calc3.update_cvd(_bars([5])[0])
    assert calc3.get_cvd_slope() == 0.0


# ---------------------------------------------------------------------------
# VolumeDeltaAnalyzer
# ---------------------------------------------------------------------------

PRICE_LL = [
    100.3,
    100.1,
    100.2,
    100.0,
    99.6,
    99.2,
    99.0,
    99.3,
    99.7,
    99.9,
    99.4,
    98.9,
    98.5,
    98.8,
    99.1,
    99.3,
    99.5,
    99.6,
    99.8,
    100.0,
]
CVD_HL = [50, 50.5, 51, 50, 48, 46, 45, 47, 49, 50, 49, 48, 47, 49, 51, 52, 53, 54, 55, 56]
PRICE_HH = [
    99.7,
    99.8,
    100.0,
    100.1,
    99.9,
    100.3,
    100.1,
    99.9,
    99.8,
    99.9,
    100.5,
    100.8,
    100.6,
    100.4,
    100.3,
    100.2,
    100.1,
    100.0,
    99.9,
    99.8,
]
CVD_LH = [40, 44, 50, 54, 56, 58, 56, 52, 48, 50, 52, 50, 47, 49, 53, 55, 57, 59, 60, 61]


def _series(values):
    return pd.Series(values, index=pd.date_range(T0, periods=len(values), freq="1min"))


def test_bullish_delta_divergence_is_detected():
    div = VolumeDeltaAnalyzer().detect_delta_divergence(_series(PRICE_LL), _series(CVD_HL))

    assert div is not None
    assert div.type == "bullish"
    assert 0 < div.strength <= 100
    assert div.price_at_signal == PRICE_LL[-1]
    assert div.delta_at_signal == CVD_HL[-1]


def test_bearish_delta_divergence_is_detected():
    div = VolumeDeltaAnalyzer().detect_delta_divergence(_series(PRICE_HH), _series(CVD_LH))

    assert div is not None
    assert div.type == "bearish"
    assert 0 < div.strength <= 100


def test_aligned_price_and_cvd_yield_no_divergence():
    analyzer = VolumeDeltaAnalyzer()

    assert analyzer.detect_delta_divergence(_series(PRICE_LL), _series(PRICE_LL)) is None
    assert analyzer.detect_delta_divergence(_series(CVD_HL), _series(CVD_HL)) is None


def test_divergence_needs_enough_history():
    analyzer = VolumeDeltaAnalyzer()
    short_p = _series(PRICE_LL).iloc[:10]
    short_c = _series(CVD_HL).iloc[:10]

    assert analyzer.detect_delta_divergence(short_p, short_c, lookback=20) is None


def test_local_extrema_finders():
    analyzer = VolumeDeltaAnalyzer()
    # Extrema must sit strictly inside the scanned range [window, len-window).
    s = _series([5, 4, 3, 4, 5, 6, 7, 6, 5, 4, 3, 4, 5, 6, 7])

    mins = analyzer._find_local_minimums(s)
    maxs = analyzer._find_local_maximums(s)

    assert 3 in mins
    assert 7 in maxs


# ---------------------------------------------------------------------------
# VolumeProfileBuilder (incl. the inf/NaN sanitisation fix)
# ---------------------------------------------------------------------------


def _profile_frame():
    # Four candles over 100.0-101.0 with the heaviest volume in the middle.
    return _candles(
        [
            (100.0, 100.5, 100.0, 100.4, 100),
            (100.4, 101.0, 100.4, 100.8, 400),
            (100.8, 101.0, 100.6, 100.7, 200),
            (100.7, 100.9, 100.5, 100.6, 100),
        ]
    )


def test_build_profile_basic_shape():
    profile = VolumeProfileBuilder(price_tick=0.25).build_profile(_profile_frame())

    assert isinstance(profile, VolumeProfile)
    assert profile.levels  # some price levels got volume
    assert profile.total_volume > 0
    prices = [lv.price for lv in profile.levels]
    assert prices == sorted(prices)
    # POC inside the traded range; value area brackets it.
    assert 100.0 <= profile.poc <= 101.0
    assert profile.val <= profile.poc <= profile.vah
    # Every level has positive volume and a delta consistent with buy/sell.
    for lv in profile.levels:
        assert lv.volume > 0
        assert lv.delta == pytest.approx(lv.buy_volume - lv.sell_volume)


def test_build_profile_empty_frame_returns_empty_profile():
    profile = VolumeProfileBuilder().build_profile(pd.DataFrame(columns=["open", "high", "low", "close", "volume"]))

    assert profile.levels == []
    assert profile.total_volume == 0
    assert profile.poc == 0 and profile.vah == 0 and profile.val == 0


def test_build_profile_ignores_inf_prices():
    """One bad candle must not take the whole profile down (the old code
    exploded in np.arange with 'Maximum allowed size exceeded')."""
    df = _profile_frame()
    df.iloc[2, df.columns.get_loc("high")] = np.inf

    profile = VolumeProfileBuilder(price_tick=0.25).build_profile(df)

    assert np.isfinite(profile.poc)
    assert np.isfinite(profile.vah) and np.isfinite(profile.val)
    assert profile.levels  # the three good candles still build a profile
    assert profile.vah <= 101.0 + 1e-9  # built from finite candles only


def test_build_profile_ignores_nan_prices():
    df = _profile_frame()
    df.iloc[1, df.columns.get_loc("low")] = np.nan  # the heavy candle goes bad

    profile = VolumeProfileBuilder(price_tick=0.25).build_profile(df)

    assert np.isfinite(profile.poc)
    assert np.isfinite(profile.vah) and np.isfinite(profile.val)
    assert profile.levels


def test_build_profile_all_non_finite_prices_returns_empty_profile():
    df = _profile_frame()
    df["low"] = np.nan
    df["high"] = np.inf

    profile = VolumeProfileBuilder().build_profile(df)

    assert profile.levels == []
    assert profile.total_volume == 0


def test_build_profile_constant_price_is_sane():
    df = _candles([(100.0, 100.0, 100.0, 100.0, 500)] * 3)

    profile = VolumeProfileBuilder(price_tick=0.25).build_profile(df)

    assert profile.levels
    assert profile.poc == pytest.approx(100.0)
    assert profile.total_volume == pytest.approx(1500)


def test_build_profile_nan_volume_is_skipped_not_fatal():
    df = _profile_frame()
    df.iloc[0, df.columns.get_loc("volume")] = np.nan

    profile = VolumeProfileBuilder(price_tick=0.25).build_profile(df)

    assert np.isfinite(profile.poc)
    assert all(np.isfinite(lv.volume) for lv in profile.levels)


def test_analyze_market_with_inf_prices_is_sane_end_to_end():
    """The user-visible outcome: ict_signal_generator.analyze_market no longer
    crashes when a candle carries an inf price (pinned as a crash before)."""
    from src.analysis.ict_signal_generator import ICTSignalGenerator
    from tests.test_ict_signal_generator import _frame

    df = _frame([100.0, 100.0, 100.0])
    df.iloc[1, df.columns.get_loc("high")] = np.inf

    result = ICTSignalGenerator().analyze_market(df)

    assert set(result.keys()) == {
        "fvgs",
        "order_blocks",
        "liquidity_pools",
        "market_structure",
        "volume_profile",
        "cvd",
        "timestamp",
    }


# ---------------------------------------------------------------------------
# ImbalanceDetector (extends the coverage in test_undefined_name_fixes.py)
# ---------------------------------------------------------------------------


def test_imbalance_detector_flags_buy_and_sell_pressure():
    detector = ImbalanceDetector(imbalance_ratio=3.0)
    # 4:1 buy pressure in every 5-bar window.
    bars = _bars([60, 60, 60, 60, 60, 60, 60])
    candles = _candles([(100, 100.5, 100, 100.4, 100)] * 7)

    imbalances = detector.detect_imbalances(bars, candles, lookback=5)

    assert imbalances
    assert all(isinstance(im, Imbalance) for im in imbalances)
    assert all(im.type == "buy" for im in imbalances)
    assert all(im.ratio >= 3.0 for im in imbalances)
    assert all(0 < im.strength <= 100 for im in imbalances)
    # Prices come from the candle closes at the matching timestamps.
    assert all(im.price == 100.4 for im in imbalances)

    sell_bars = _bars([-60] * 7)
    sell_imbalances = detector.detect_imbalances(sell_bars, candles, lookback=5)
    assert sell_imbalances
    assert all(im.type == "sell" for im in sell_imbalances)


def test_imbalance_detector_balanced_flow_yields_nothing():
    detector = ImbalanceDetector(imbalance_ratio=3.0)

    assert detector.detect_imbalances(_bars([0] * 8), lookback=5) == []


def test_imbalance_detector_short_history_yields_nothing():
    detector = ImbalanceDetector(imbalance_ratio=3.0)

    assert detector.detect_imbalances(_bars([60, 60, 60]), lookback=5) == []


def test_imbalance_detector_price_falls_back_positionally():
    detector = ImbalanceDetector(imbalance_ratio=3.0)
    bars = _bars([60] * 6)
    candles = _candles(
        [(100 + i, 100.5 + i, 100 + i, 100.2 + i, 100) for i in range(8)], start=T0 - timedelta(minutes=4)
    )

    imbalances = detector.detect_imbalances(bars, candles, lookback=5)

    assert imbalances
    # The two windows end at timestamps absent from the candle index, so the
    # positional fallback close (iloc[i + lookback - 1]) is used: iloc[4], iloc[5].
    assert {im.price for im in imbalances} == {100.2 + 4, 100.2 + 5}


# ---------------------------------------------------------------------------
# AbsorptionDetector
# ---------------------------------------------------------------------------


def _absorption_frame():
    rows = [(100.0, 100.1, 99.9, 100.02, 100)] * 19
    # A high-volume doji: 4x volume, ~0 price change -> absorption.
    rows.append((100.0, 100.05, 99.95, 100.01, 400))
    return _candles(rows)


def test_absorption_detected_on_high_volume_doji():
    events = AbsorptionDetector().detect_absorption(_absorption_frame())

    assert events
    ts, kind = events[0]
    assert ts == _absorption_frame().index[-1]
    assert kind in ("buy_absorption", "sell_absorption")


def test_absorption_direction_follows_candle_close():
    rows = [(100.0, 100.1, 99.9, 100.02, 100)] * 19
    rows.append((100.0, 100.05, 99.95, 100.04, 400))  # closes up
    up = AbsorptionDetector().detect_absorption(_candles(rows))
    rows[-1] = (100.0, 100.05, 99.95, 99.96, 400)  # closes down
    down = AbsorptionDetector().detect_absorption(_candles(rows))

    assert up[-1][1] == "buy_absorption"
    assert down[-1][1] == "sell_absorption"


def test_absorption_skips_normal_and_short_frames():
    detector = AbsorptionDetector()

    normal = _candles([(100.0, 100.4, 99.6, 100.2, 100)] * 30)  # big moves
    assert detector.detect_absorption(normal) == []

    short = _candles([(100.0, 100.05, 99.95, 100.0, 500)] * 5)
    assert detector.detect_absorption(short) == []


def test_absorption_ignores_warmup_nans():
    rows = [(100.0, 100.1, 99.9, 100.02, 100)] * 30
    rows[0] = (100.0, 100.1, 99.9, 100.02, np.nan)  # breaks the first rolling means
    df = _candles(rows)

    events = AbsorptionDetector().detect_absorption(df)

    assert all(not pd.isna(ts) for ts, _ in events)
