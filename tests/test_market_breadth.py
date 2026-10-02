"""Offline coverage for src/data/market_breadth.py.

The module pulls yfinance data (``yf.Ticker(...).history(...)``) for
advance/decline, new highs/lows, TICK proxy, VOLD and McClellan indicators.
Every network touch is faked here:

* computation tests patch ``_get_intraday_stats`` on the instance (pure logic)
* seam tests patch the module's ``yf`` attribute with a fake Ticker factory
  keyed by symbol, dispatching on ``period``

Callers (src/api/routers/market.py, src/llm/tools/data_tools.py,
src/scheduler/scheduler.py) rely on: the indicator keys produced by
``get_market_internals``, the ``source: "mock"`` label on the fallback
payload, and interpretation strings — all pinned below.

Tests marked ``test_bug_*`` fail on the pre-fix module (proven against a
HEAD copy in the cycle-8 report); the rest pin existing correct behaviour
and pass on both versions.
"""

from __future__ import annotations

import math

import numpy as np
import pandas as pd

from src.data import market_breadth as breadth_mod
from src.data.market_breadth import MarketBreadthCollector


def _stats(changes, volumes=None):
    """Fake ``_get_intraday_stats`` return value."""
    return {"changes": list(changes), "volumes": list(volumes if volumes is not None else [1_000_000] * len(changes))}


def _collector_with(monkeypatch, nyse=None, nasdaq=None):
    """Collector whose intraday stats are pinned (no network)."""
    c = MarketBreadthCollector()
    by_exchange = {
        tuple(c.nyse_symbols): _stats(*(nyse or ([], []))),
        tuple(c.nasdaq_symbols): _stats(*(nasdaq or ([], []))),
    }

    def fake(symbols):
        return by_exchange[tuple(symbols)]

    monkeypatch.setattr(c, "_get_intraday_stats", fake)
    return c


# ---------------------------------------------------------------------------
# Pure interpretation helpers (thresholds are strict > / <)
# ---------------------------------------------------------------------------


def test_interpret_ad_ratio_bands():
    f = MarketBreadthCollector()._interpret_ad_ratio
    assert f(2.1, 2.1) == "Very Bullish"
    assert f(2.0, 2.0) == "Bullish"  # boundary not inclusive
    assert f(1.6, 1.6) == "Bullish"
    assert f(1.5, 1.5) == "Neutral"
    assert f(0.7, 0.7) == "Neutral"
    assert f(0.67, 0.67) == "Bearish"
    assert f(0.55, 0.55) == "Bearish"
    assert f(0.5, 0.5) == "Very Bearish"


def test_interpret_tick_vold_mcclellan_bands():
    c = MarketBreadthCollector()
    assert c._interpret_tick(601) == "Very Bullish"
    assert c._interpret_tick(600) == "Bullish"
    assert c._interpret_tick(200) == "Neutral"
    assert c._interpret_tick(-200) == "Bearish"
    assert c._interpret_tick(-600) == "Very Bearish"
    assert c._interpret_vold(6e8) == "Strong Buying"
    assert c._interpret_vold(5e8) == "Moderate Buying"
    assert c._interpret_vold(1e8) == "Neutral"
    assert c._interpret_vold(-1e8) == "Moderate Selling"
    assert c._interpret_vold(-5e8) == "Strong Selling"
    assert c._interpret_mcclellan(101, 0) == "Overbought"
    assert c._interpret_mcclellan(100, 0) == "Bullish"
    assert c._interpret_mcclellan(50, 0) == "Neutral"
    assert c._interpret_mcclellan(-50, 0) == "Bearish"
    assert c._interpret_mcclellan(-100, 0) == "Oversold"


def test_calculate_ema_fallbacks_and_constant():
    c = MarketBreadthCollector()
    assert c._calculate_ema([], 5) == 0
    assert c._calculate_ema([2.0, 4.0], 5) == 3.0  # shorter than period -> mean
    assert c._calculate_ema([7.0] * 30, 19) == 7.0  # constant series -> constant


# ---------------------------------------------------------------------------
# _calculate_advance_decline (logic level)
# ---------------------------------------------------------------------------


def test_advance_decline_counts_ratios_net(monkeypatch):
    c = _collector_with(
        monkeypatch,
        nyse=([1.0, -1.0, 1.0, 0.0], [100, 200, 300, 400]),
        nasdaq=([-1.0, -1.0, 1.0, 1.0], [10, 20, 30, 40]),
    )
    out = c._calculate_advance_decline()
    assert out["nyse_advancing"] == 2
    assert out["nyse_declining"] == 1
    assert out["nyse_unchanged"] == 1
    assert out["nyse_ad_ratio"] == 2.0
    assert out["nyse_net_ad"] == 1
    assert out["nasdaq_advancing"] == 2
    assert out["nasdaq_declining"] == 2
    assert out["nasdaq_ad_ratio"] == 1.0
    assert out["nasdaq_net_ad"] == 0
    # net A/D recorded for McClellan
    assert len(c.ad_history) == 1
    assert c.ad_history[-1]["net_ad"] == 1


def test_advance_decline_history_trimmed_to_max(monkeypatch):
    c = _collector_with(monkeypatch)
    c.ad_history = [{"date": None, "net_ad": 1}] * c.max_history
    c._calculate_advance_decline()
    assert len(c.ad_history) == c.max_history


def test_bug_ad_ratio_all_advancing_is_bullish_not_zero(monkeypatch):
    # 10 advancing, 0 declining on NYSE; balanced NASDAQ. Old code reported
    # ratio 0.0 (the most bearish reading) for the most bullish state.
    c = _collector_with(
        monkeypatch,
        nyse=([1.0] * 10, [1] * 10),
        nasdaq=([1.0, -1.0] * 4, [1] * 8),
    )
    out = c._calculate_advance_decline()
    assert out["nyse_ad_ratio"] == 10.0  # count proxy when nothing declines
    assert "Bullish" in out["interpretation"]


def test_bug_ad_ratio_no_data_is_neutral_not_bearish(monkeypatch):
    c = _collector_with(monkeypatch)  # no symbols returned anything
    out = c._calculate_advance_decline()
    assert out["nyse_ad_ratio"] == 1.0
    assert out["nasdaq_ad_ratio"] == 1.0
    assert out["interpretation"] == "Neutral"


# ---------------------------------------------------------------------------
# TICK / VOLD (logic level)
# ---------------------------------------------------------------------------


def test_tick_proxy_normalization(monkeypatch):
    c = _collector_with(
        monkeypatch,
        nyse=([1.0] * 10, [1] * 10),
        nasdaq=([-1.0] * 8, [1] * 8),
    )
    out = c._calculate_tick_proxy()
    # 10 up, 8 down over 18 symbols -> (2/18)*1000
    assert out["tick_value"] == int((2 / 18) * 1000)
    assert out["tick_30min_avg"] == out["tick_value"]


def test_vold_up_minus_down_volume(monkeypatch):
    c = _collector_with(
        monkeypatch,
        nyse=([1.0, -1.0, 0.0], [100, 50, 999]),
        nasdaq=([-1.0, 1.0], [200, 100]),
    )
    out = c._calculate_vold()
    assert out["nyse_vold"] == 50  # unchanged volume excluded
    assert out["nasdaq_vold"] == -100
    assert out["total_vold"] == -50


# ---------------------------------------------------------------------------
# McClellan (logic level)
# ---------------------------------------------------------------------------


def test_mcclellan_insufficient_history():
    c = MarketBreadthCollector()
    c.ad_history = [{"date": None, "net_ad": 1}] * 38
    out = c._calculate_mcclellan()
    assert out["interpretation"] == "Insufficient data"
    assert out["mcclellan_oscillator"] == 0


def test_mcclellan_flat_history_is_zero_rising_is_positive():
    flat = MarketBreadthCollector()
    flat.ad_history = [{"date": None, "net_ad": 10}] * 50
    assert flat._calculate_mcclellan()["mcclellan_oscillator"] == 0.0

    rising = MarketBreadthCollector()
    rising.ad_history = [{"date": None, "net_ad": float(i)} for i in range(50)]
    assert rising._calculate_mcclellan()["mcclellan_oscillator"] > 0


# ---------------------------------------------------------------------------
# _get_intraday_stats / _calculate_highs_lows (yfinance seam level)
# ---------------------------------------------------------------------------


class _FakeYf:
    """Fake yfinance module: Ticker(symbol).history(period=...) -> frame."""

    def __init__(self, frames):
        self.frames = frames
        self.calls: list[tuple[str, str | None]] = []

    class _Ticker:
        def __init__(self, outer, symbol):
            self._outer = outer
            self._symbol = symbol

        def history(self, period=None, interval=None):
            self._outer.calls.append((self._symbol, period))
            return self._outer.frames.get(self._symbol, pd.DataFrame())

    def Ticker(self, symbol):
        return self._Ticker(self, symbol)


def _daily_frame(closes, highs=None, lows=None, volumes=None):
    n = len(closes)
    return pd.DataFrame(
        {
            "Close": pd.Series(closes, dtype="float64"),
            "High": pd.Series(highs if highs is not None else [max(closes) + 1.0] * n, dtype="float64"),
            "Low": pd.Series(lows if lows is not None else [min(closes) - 1.0] * n, dtype="float64"),
            "Volume": pd.Series(volumes if volumes is not None else [1_000_000] * n, dtype="float64"),
        }
    )


def test_get_intraday_stats_computes_change_and_volume(monkeypatch):
    frames = {"SPY": _daily_frame([100.0, 102.0])}
    fake = _FakeYf(frames)
    monkeypatch.setattr(breadth_mod, "yf", fake)
    out = MarketBreadthCollector()._get_intraday_stats(["SPY", "NOPE"])
    assert out["changes"] == [2.0]
    assert out["volumes"] == [1_000_000.0]  # NOPE (empty frame) skipped
    assert out["changes"] == [2.0]  # one-row frames would be skipped too
    frames["ONE"] = _daily_frame([100.0])
    out2 = MarketBreadthCollector()._get_intraday_stats(["ONE"])
    assert out2["changes"] == []


def test_bug_get_intraday_stats_skips_nan_close(monkeypatch):
    frames = {"SPY": _daily_frame([100.0, math.nan])}
    monkeypatch.setattr(breadth_mod, "yf", _FakeYf(frames))
    out = MarketBreadthCollector()._get_intraday_stats(["SPY"])
    assert out["changes"] == []  # NaN row skipped, not recorded as unchanged
    assert out["volumes"] == []


def test_bug_get_intraday_stats_skips_nan_volume(monkeypatch):
    frames = {"SPY": _daily_frame([100.0, 102.0], volumes=[1_000_000.0, math.nan])}
    monkeypatch.setattr(breadth_mod, "yf", _FakeYf(frames))
    out = MarketBreadthCollector()._get_intraday_stats(["SPY"])
    assert out["changes"] == []
    assert out["volumes"] == []


def test_highs_lows_near_high_low_neither(monkeypatch):
    base = [100.0 + i for i in range(200)]
    frames = {
        "SPY": _daily_frame(base),  # rising -> last close near year high
        "DIA": _daily_frame(list(reversed(base))),  # falling -> near year low
        # mid-range: close 100 vs year high 120 / low 80 -> near neither
        "IWM": _daily_frame([100.0] * 200, highs=[120.0] * 200, lows=[80.0] * 200),
    }
    monkeypatch.setattr(breadth_mod, "yf", _FakeYf(frames))
    c = MarketBreadthCollector()
    c.nyse_symbols = ["SPY", "DIA", "IWM"]
    c.nasdaq_symbols = []
    out = c._calculate_highs_lows()
    assert out["new_highs"] == 1
    assert out["new_lows"] == 1
    assert out["net_hl"] == 0
    assert out["hl_ratio"] == 1.0
    assert out["interpretation"] == "Neutral"


def test_highs_lows_short_history_skipped(monkeypatch):
    frames = {"SPY": _daily_frame([100.0] * 150)}  # < 200 rows
    monkeypatch.setattr(breadth_mod, "yf", _FakeYf(frames))
    c = MarketBreadthCollector()
    c.nyse_symbols = ["SPY"]
    c.nasdaq_symbols = []
    out = c._calculate_highs_lows()
    assert out["new_highs"] == 0 and out["new_lows"] == 0


def test_highs_lows_all_highs_ratio_falls_back_to_count(monkeypatch):
    # Pinned existing convention: 0 lows -> hl_ratio reports the count.
    frames = {"SPY": _daily_frame([100.0 + i for i in range(200)])}
    monkeypatch.setattr(breadth_mod, "yf", _FakeYf(frames))
    c = MarketBreadthCollector()
    c.nyse_symbols = ["SPY"]
    c.nasdaq_symbols = []
    out = c._calculate_highs_lows()
    assert out["new_highs"] == 1
    assert out["hl_ratio"] == 1
    assert out["interpretation"] == "Bullish"


# ---------------------------------------------------------------------------
# get_market_internals end-to-end (fully faked yf)
# ---------------------------------------------------------------------------


def _full_fake_yf():
    frames = {}
    for sym in MarketBreadthCollector().nyse_symbols + MarketBreadthCollector().nasdaq_symbols:
        rising = [100.0 + i * 0.5 for i in range(250)]
        frames[sym] = _daily_frame(rising)
    return _FakeYf(frames)


def test_get_market_internals_full_payload(monkeypatch):
    monkeypatch.setattr(breadth_mod, "yf", _full_fake_yf())
    out = MarketBreadthCollector().get_market_internals()
    for key in (
        "nyse_advancing",
        "nyse_ad_ratio",
        "new_highs",
        "hl_ratio",
        "tick_value",
        "nyse_vold",
        "total_vold",
        "mcclellan_oscillator",
        "interpretation",
    ):
        assert key in out, key
    assert out.get("source") != "mock"  # live path, not the fallback


def test_get_market_internals_exception_falls_back_to_labelled_mock(monkeypatch):
    c = MarketBreadthCollector()

    def boom():
        raise RuntimeError("network down")

    monkeypatch.setattr(c, "_calculate_advance_decline", boom)
    out = c.get_market_internals()
    assert out["source"] == "mock"
    assert out["classification"] == "mock"
    assert out["nyse_advancing"] == 1520  # exchange-scale placeholder payload


def test_mock_internals_labelled():
    out = MarketBreadthCollector()._get_mock_internals()
    assert out["source"] == "mock"
    assert "nyse_vold" in out and "mcclellan_oscillator" in out


def test_get_market_breadth_convenience(monkeypatch):
    monkeypatch.setattr(breadth_mod, "yf", _full_fake_yf())
    out = breadth_mod.get_market_breadth()
    assert "nyse_advancing" in out


# ---------------------------------------------------------------------------
# Robustness: numpy types survive the round trip
# ---------------------------------------------------------------------------


def test_numpy_floats_flow_through(monkeypatch):
    c = _collector_with(
        monkeypatch,
        nyse=([np.float64(1.5), np.float64(-0.5)], [np.float64(100.0), np.float64(50.0)]),
        nasdaq=([np.float64(-1.0)], [np.float64(10.0)]),
    )
    out = c._calculate_advance_decline()
    assert out["nyse_advancing"] == 1
    assert math.isfinite(out["nyse_ad_ratio"])
    vold = c._calculate_vold()
    assert vold["nyse_vold"] == 50
