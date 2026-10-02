"""Offline tests for src/llm/tools/upstream_tools.py (agent tool wrappers).

Every upstream network/analysis client is faked: scan_for_divergences,
ICTSignalGenerator and OptionsScreener are monkeypatched at their source
modules (the tools import them lazily at call time). TechnicalIndicators runs
for real -- it is pure pandas. No network, no live providers.
"""

from __future__ import annotations

import json
import math
from datetime import datetime
from types import SimpleNamespace

import pytest

from src.llm.tools.upstream_tools import (
    UPSTREAM_TOOL_DEFINITIONS,
    UPSTREAM_TOOL_HANDLERS,
    analyze_order_flow,
    calculate_risk_metrics,
    classify_regime,
    compute_indicators,
    detect_divergences,
    generate_ict_signals,
    screen_options_flow,
)

# ---------------------------------------------------------------------------
# Fakes / helpers
# ---------------------------------------------------------------------------


def _candles(n: int, *, upper: bool = False, close_override=None, volume_override=None) -> list[dict]:
    """Deterministic OHLCV candles in the get_ohlcv JSON shape."""
    out = []
    for i in range(n):
        close = close_override(i) if close_override else 100.0 + i * 0.5
        vol = volume_override(i) if volume_override else 1_000.0
        row = {
            "timestamp": f"2024-01-{i % 28 + 1:02d}T00:00:00",
            "open": close - 0.25,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": vol,
        }
        if upper:
            row = {k.upper(): v for k, v in row.items()}
        out.append(row)
    return out


def _ohlcv_json(n: int, **kwargs) -> str:
    return json.dumps({"candles": _candles(n, **kwargs)})


def _fake_scan_result(divergences=None):
    divergences = divergences or []
    return {
        "total_divergences": len(divergences),
        "by_type": {
            "regular_bullish": 2,
            "regular_bearish": 1,
            "hidden_bullish": 0,
            "hidden_bearish": 3,
        },
        "divergences": divergences,
        "strongest": None,
        "signal": "BULLISH",
    }


@pytest.fixture
def fake_scan(monkeypatch):
    """Patch the detector at its source module; records the frame it receives."""
    import src.analysis.divergence_detector as detector_mod

    captured: dict = {}

    def _scan(df, min_strength=60.0):
        captured["df"] = df
        return _fake_scan_result()

    monkeypatch.setattr(detector_mod, "scan_for_divergences", _scan)
    return captured


# ---------------------------------------------------------------------------
# detect_divergences
# ---------------------------------------------------------------------------


async def test_detect_divergences_maps_by_type_counts(fake_scan):
    """The detector result nests counts under by_type -- they must surface."""
    result = await detect_divergences("TEST", _ohlcv_json(40))

    assert "error" not in result
    assert result["symbol"] == "TEST"
    assert result["divergences_found"] == 0  # total_divergences of the fake
    assert result["regular_bullish"] == 2
    assert result["regular_bearish"] == 1
    assert result["hidden_bullish"] == 0
    assert result["hidden_bearish"] == 3
    assert result["timestamp"]


async def test_detect_divergences_passes_the_frame_and_min_strength(fake_scan, monkeypatch):
    import src.analysis.divergence_detector as detector_mod

    seen: dict = {}

    def scan(df, min_strength=60.0):
        seen["columns"] = list(df.columns)
        seen["min_strength"] = min_strength
        return _fake_scan_result()

    monkeypatch.setattr(detector_mod, "scan_for_divergences", scan)

    await detect_divergences("TEST", _ohlcv_json(40, upper=True))

    # Uppercase columns are normalised to lowercase before scanning.
    assert {"open", "high", "low", "close", "volume"} <= set(seen["columns"])
    assert seen["min_strength"] == 60.0


async def test_detect_divergences_needs_30_candles():
    result = await detect_divergences("TEST", _ohlcv_json(29))

    assert result == {"error": "Need >=30 candles, got 29"}


async def test_detect_divergences_invalid_json_is_an_error():
    result = await detect_divergences("TEST", "not json{")

    assert "error" in result


async def test_detect_divergences_truncates_details_to_10(fake_scan, monkeypatch):
    import src.analysis.divergence_detector as detector_mod

    many = [{"type": "regular_bullish", "indicator": "rsi", "strength": 70.0} for _ in range(15)]
    monkeypatch.setattr(detector_mod, "scan_for_divergences", lambda df, m=60.0: _fake_scan_result(many))

    result = await detect_divergences("TEST", _ohlcv_json(40))

    assert len(result["details"]) == 10


# ---------------------------------------------------------------------------
# generate_ict_signals
# ---------------------------------------------------------------------------


def _fake_ict_signal(**overrides):
    base = SimpleNamespace(
        type="long",
        confidence=80.0,
        entry_price=100.0,
        stop_loss=95.0,
        take_profit=[110.0, 115.0],
        trigger="FVG retest with CVD confirmation " * 5,
        risk_reward_ratio=2.5,
    )
    return SimpleNamespace(**{**base.__dict__, **overrides})


@pytest.fixture
def fake_ict(monkeypatch):
    """Patch the generator class at its source module."""
    import src.analysis.ict_signal_generator as ict_mod

    holder: dict = {"signals": [_fake_ict_signal()]}

    class _FakeGenerator:
        def generate_signals(self, candles, market_analysis=None):
            holder["candles"] = candles
            return holder["signals"]

    monkeypatch.setattr(ict_mod, "ICTSignalGenerator", _FakeGenerator)
    return holder


async def test_generate_ict_signals_maps_signal_fields(fake_ict):
    result = await generate_ict_signals("TEST", _ohlcv_json(30))

    assert "error" not in result
    assert result["symbol"] == "TEST"
    assert result["signal_count"] == 1
    signal = result["signals"][0]
    assert signal["type"] == "long"
    assert signal["confidence"] == 80.0
    assert signal["entry"] == 100.0
    assert signal["stop"] == 95.0
    assert signal["targets"] == [110.0, 115.0]
    assert signal["rr_ratio"] == 2.5
    assert len(signal["trigger"]) <= 120  # truncated


async def test_generate_ict_signals_caps_at_5(fake_ict):
    fake_ict["signals"] = [_fake_ict_signal(confidence=float(i)) for i in range(8)]

    result = await generate_ict_signals("TEST", _ohlcv_json(30))

    assert result["signal_count"] == 8
    assert len(result["signals"]) == 5


async def test_generate_ict_signals_with_no_signals(fake_ict):
    fake_ict["signals"] = []

    result = await generate_ict_signals("TEST", _ohlcv_json(30))

    assert result["signal_count"] == 0
    assert result["signals"] == []


async def test_generate_ict_signals_needs_20_candles():
    result = await generate_ict_signals("TEST", _ohlcv_json(19))

    assert result == {"error": "Need >=20 candles, got 19"}


# ---------------------------------------------------------------------------
# compute_indicators
# ---------------------------------------------------------------------------


async def test_compute_indicators_returns_current_values():
    """Runs the real (pure pandas) TechnicalIndicators on 60 candles."""
    result = await compute_indicators("TEST", _ohlcv_json(60))

    assert "error" not in result
    indicators = result["indicators"]
    assert 0 <= indicators["rsi"] <= 100
    assert indicators["sma_20"] > 0
    assert "macd" in indicators and "macd_signal" in indicators
    assert indicators["atr"] > 0
    assert result["timestamp"]


async def test_compute_indicators_skips_nan_columns():
    """Short history -> SMA200/ADX are NaN and must be omitted, not crash."""
    result = await compute_indicators("TEST", _ohlcv_json(25))

    assert "error" not in result
    assert "sma_200" not in result["indicators"]
    assert "adx" not in result["indicators"]
    assert "sma_20" in result["indicators"]


async def test_compute_indicators_needs_20_candles():
    result = await compute_indicators("TEST", _ohlcv_json(19))

    assert result == {"error": "Need >=20 candles, got 19"}


async def test_compute_indicators_normalises_uppercase_columns():
    result = await compute_indicators("TEST", _ohlcv_json(60, upper=True))

    assert "error" not in result
    assert "rsi" in result["indicators"]


# ---------------------------------------------------------------------------
# classify_regime
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "price,vix,atr,volume,avg_volume,expected",
    [
        (100.0, 30.0, 3.0, 0, 0, "CHOPPY_AVOID"),  # high vix + wide range
        (100.0, 30.0, 1.0, 0, 0, "TRENDING_BEARISH"),  # high vix, tight range
        (100.0, 12.0, 1.0, 0, 0, "TRENDING_BULLISH"),  # low vix, tight range
        (100.0, 12.0, 2.0, 0, 0, "RANGE_BOUND"),  # low vix, wide range
        (100.0, 18.0, 3.0, 0, 0, "CHOPPY_AVOID"),  # mid vix, very wide range
        (100.0, 18.0, 1.0, 300, 100, "BREAKOUT_PENDING"),  # volume expansion
        (100.0, 18.0, 1.0, 100, 100, "RANGE_BOUND"),  # nothing distinctive
    ],
)
async def test_classify_regime_branches(price, vix, atr, volume, avg_volume, expected):
    result = await classify_regime("TEST", price, vix, atr, volume, avg_volume)

    assert result["regime"] == expected
    assert result["symbol"] == "TEST"
    assert result["description"]  # every regime has a description


async def test_classify_regime_volume_ratio_none_without_average():
    result = await classify_regime("TEST", 100.0, 18.0, 1.0, 500, 0)

    assert result["volume_ratio"] is None
    assert result["atr_pct"] == 1.0


async def test_classify_regime_zero_price_guards_division():
    result = await classify_regime("TEST", 0.0, 18.0, 1.0)

    assert result["atr_pct"] == 0


# ---------------------------------------------------------------------------
# calculate_risk_metrics
# ---------------------------------------------------------------------------


async def test_calculate_risk_metrics_position_sizing():
    result = await calculate_risk_metrics(entry_price=100.0, stop_loss=95.0, account_size=25_000, risk_percent=1.0)

    assert result["risk_per_share"] == 5.0
    assert result["risk_amount"] == 250.0
    assert result["position_size_shares"] == 50
    assert result["total_position_value"] == 5000.0
    assert result["leverage"] == 0.2


async def test_calculate_risk_metrics_defaults():
    result = await calculate_risk_metrics(entry_price=50.0, stop_loss=49.0)

    assert result["account_size"] == 25_000
    assert result["risk_percent"] == 1.0
    assert result["position_size_shares"] == 250


async def test_calculate_risk_metrics_same_price_is_error():
    result = await calculate_risk_metrics(entry_price=100.0, stop_loss=100.0)

    assert "error" in result


async def test_calculate_risk_metrics_nan_input_is_error():
    result = await calculate_risk_metrics(entry_price=math.nan, stop_loss=100.0)

    assert "error" in result


# ---------------------------------------------------------------------------
# screen_options_flow
# ---------------------------------------------------------------------------


@pytest.fixture
def fake_screener(monkeypatch):
    import src.analysis.options_screener as screener_mod

    holder: dict = {"calls": [], "result": []}

    class _FakeScreener:
        def screen_with_macro_filter(self, symbols, strategy_preference=None):
            holder["calls"].append((symbols, strategy_preference))
            return holder["result"]

    monkeypatch.setattr(screener_mod, "OptionsScreener", _FakeScreener)
    return holder


async def test_screen_options_flow_maps_opportunities(fake_screener):
    fake_screener["result"] = [
        SimpleNamespace(
            symbol="SPY",
            strike=600.0,
            expiry=datetime(2024, 6, 21),
            option_type="call",
            premium=1.5,
            volume=10_000,
            open_interest=5_000,
        )
    ]

    result = await screen_options_flow("SPY, QQQ,", strategy="directional")

    assert result["symbols_screened"] == ["SPY", "QQQ"]
    assert result["strategy"] == "directional"
    opp = result["opportunities"][0]
    assert opp["symbol"] == "SPY"
    assert opp["strike"] == 600.0
    assert opp["expiry"] == "2024-06-21 00:00:00"
    assert opp["type"] == "call"
    assert fake_screener["calls"] == [(["SPY", "QQQ"], "directional")]


async def test_screen_options_flow_empty_result(fake_screener):
    result = await screen_options_flow("SPY")

    assert result["opportunities"] == []


# ---------------------------------------------------------------------------
# analyze_order_flow
# ---------------------------------------------------------------------------


async def test_analyze_order_flow_bullish_cvd_and_rising_volume():
    """Closes above opens -> positive cumulative delta; volume ramps up."""
    result = await analyze_order_flow(
        "TEST",
        _ohlcv_json(20, close_override=lambda i: 100.0 + i, volume_override=lambda i: 100.0 + i * 10),
    )

    assert "error" not in result
    assert result["cvd_slope"] == "bullish"
    assert result["cumulative_delta"] > 0
    assert result["volume_trend"] == "increasing"
    assert result["candles_analyzed"] == 20


async def test_analyze_order_flow_absorption():
    """Flat price with a late volume spike reads as absorption."""
    result = await analyze_order_flow(
        "TEST",
        _ohlcv_json(
            20,
            close_override=lambda i: 100.0 + (0.05 if i % 2 else -0.05),
            volume_override=lambda i: 100.0 if i < 15 else 5_000.0,
        ),
    )

    assert result["absorption_detected"] is True


async def test_analyze_order_flow_needs_10_candles():
    result = await analyze_order_flow("TEST", _ohlcv_json(9))

    assert result == {"error": "Need >=10 candles, got 9"}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------


def test_every_definition_has_a_handler_and_vice_versa():
    def_names = {d["function"]["name"] for d in UPSTREAM_TOOL_DEFINITIONS}
    handler_names = set(UPSTREAM_TOOL_HANDLERS)

    assert def_names == handler_names
    assert len(UPSTREAM_TOOL_DEFINITIONS) == 7
