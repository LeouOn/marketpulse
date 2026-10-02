"""Offline tests for src/llm/tools/technical_tools.py (agent tool wrappers).

`analyze_symbol_technicals` runs the real (pure pandas) OHLCAnalyzer on
deterministic candles; `find_support_resistance` is pure computation. The only
faked seam is OHLCAnalyzer itself (for the error-path test). No network, no
live providers. Candle shape mirrors what get_ohlcv actually returns
(time/open/high/low/close/volume, capped at 50).
"""

from __future__ import annotations

import json
import math

from src.llm.tools.technical_tools import (
    TECHNICAL_TOOL_DEFINITIONS,
    TECHNICAL_TOOL_HANDLERS,
    _dedupe_levels,
    _nearest_level,
    analyze_symbol_technicals,
    find_support_resistance,
)

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _candles(n: int, *, highs=None, lows=None, closes=None) -> list[dict]:
    """Deterministic candles; per-series overrides for pivot/NaN crafting."""
    out = []
    for i in range(n):
        close = closes(i) if closes else 100.0 + (i % 4) * 0.5 - 1.0
        out.append(
            {
                "time": f"2024-01-{i % 28 + 1:02d}T00:00:00",
                "open": close - 0.25,
                "high": highs(i) if highs else close + 1.0,
                "low": lows(i) if lows else close - 1.0,
                "close": close,
                "volume": 1_000.0,
            }
        )
    return out


def _ohlcv_json(n: int, *, interval: str = "1d", **kwargs) -> str:
    return json.dumps({"symbol": "TEST", "period": "3mo", "interval": interval, "candles": _candles(n, **kwargs)})


# ---------------------------------------------------------------------------
# analyze_symbol_technicals
# ---------------------------------------------------------------------------


async def test_analyze_symbol_technicals_happy_path():
    result = await analyze_symbol_technicals("TEST", _ohlcv_json(40))

    assert "error" not in result
    assert result["symbol"] == "TEST"
    assert result["timeframe_count"] >= 1
    assert isinstance(result["overall_strength"], (int, float))
    assert result["overall_trend"]
    assert result["timestamp"]
    # Trimmed lists, not unbounded dumps.
    assert len(result["patterns"]) <= 10
    assert len(result["signals"]) <= 10


async def test_analyze_symbol_technicals_propagates_analyzer_errors(monkeypatch):
    """An analyzer failure must surface as an error, not a NEUTRAL 'success'."""
    import src.analysis.ohlc_analyzer as analyzer_mod

    class _BrokenAnalyzer:
        def analyze_symbol(self, data, symbol):
            return {"symbol": symbol, "error": "analysis exploded", "timestamp": "x"}

    monkeypatch.setattr(analyzer_mod, "OHLCAnalyzer", _BrokenAnalyzer)

    result = await analyze_symbol_technicals("TEST", _ohlcv_json(40))

    assert result.get("error") == "analysis exploded"


async def test_analyze_symbol_technicals_maps_unsupported_intervals():
    """get_ohlcv can return '1h' candles; they must still get analysed."""
    result = await analyze_symbol_technicals("TEST", _ohlcv_json(40, interval="1h"))

    assert "error" not in result
    assert result["timeframe_count"] >= 1


async def test_analyze_symbol_technicals_rejects_non_dict_json():
    result = await analyze_symbol_technicals("TEST", json.dumps([1, 2, 3]))

    assert "Invalid OHLCV data format" in result["error"]
    assert "do not fabricate" in result["error"]


async def test_analyze_symbol_technicals_invalid_json_is_error():
    result = await analyze_symbol_technicals("TEST", "not json{")

    assert "error" in result


async def test_analyze_symbol_technicals_empty_candles_is_neutral():
    """Fewer than 10 candles -> no timeframes analysed, but no error either."""
    result = await analyze_symbol_technicals("TEST", json.dumps({"candles": [], "interval": "1d"}))

    assert "error" not in result
    assert result["timeframe_count"] == 0
    assert result["overall_trend"] == "NEUTRAL"
    assert result["overall_strength"] == 0


# ---------------------------------------------------------------------------
# find_support_resistance
# ---------------------------------------------------------------------------


def _sr_json(highs, lows, closes) -> str:
    n = len(highs)
    candles = [
        {
            "time": f"2024-01-{i % 28 + 1:02d}",
            "open": closes[i] - 0.25,
            "high": highs[i],
            "low": lows[i],
            "close": closes[i],
            "volume": 1_000.0,
        }
        for i in range(n)
    ]
    return json.dumps({"symbol": "TEST", "interval": "1d", "candles": candles})


def _flat(n, value):
    return [value] * n


async def test_find_support_resistance_detects_pivots():
    n = 20
    highs = _flat(n, 101.0)
    highs[5] = 110.0
    highs[12] = 105.0
    lows = _flat(n, 99.0)
    lows[8] = 90.0
    closes = _flat(n, 100.0)

    result = await find_support_resistance("TEST", _sr_json(highs, lows, closes))

    assert "error" not in result
    assert result["current_price"] == 100.0
    resistance_levels = [r["level"] for r in result["resistances"]]
    assert 110.0 in resistance_levels and 105.0 in resistance_levels
    support_levels = [s["level"] for s in result["supports"]]
    assert 90.0 in support_levels
    assert result["nearest_resistance"]["level"] == 105.0
    assert result["nearest_support"]["level"] == 90.0
    assert all(r["type"] == "resistance" for r in result["resistances"])
    assert all(s["type"] == "support" for s in result["supports"])


async def test_find_support_resistance_needs_10_candles():
    result = await find_support_resistance("TEST", _ohlcv_json(9))

    assert result == {"error": "Need at least 10 candles, got 9"}


async def test_find_support_resistance_rejects_non_dict_json():
    result = await find_support_resistance("TEST", json.dumps([1, 2, 3]))

    assert "Invalid OHLCV data format" in result["error"]


async def test_find_support_resistance_normalises_uppercase_columns():
    candles = [
        {"TIME": f"2024-01-{i % 28 + 1:02d}", "Open": 99.0, "High": 101.0, "Low": 98.0, "Close": 100.0, "Volume": 10.0}
        for i in range(12)
    ]

    result = await find_support_resistance("TEST", json.dumps({"candles": candles}))

    assert "error" not in result
    assert result["current_price"] == 100.0


async def test_find_support_resistance_nan_close_gives_none_price():
    """A NaN latest close must come back as null, not as a NaN float."""
    n = 12
    highs = _flat(n, 101.0)
    lows = _flat(n, 99.0)
    closes = _flat(n, 100.0)
    closes[-1] = math.nan

    result = await find_support_resistance("TEST", _sr_json(highs, lows, closes))

    assert "error" not in result
    assert result["current_price"] is None


async def test_find_support_resistance_survives_zero_levels():
    """A legitimate 0.0 pivot low must not crash level deduplication."""
    n = 20
    highs = _flat(n, 101.0)
    lows = _flat(n, 99.0)
    lows[5] = 0.0
    lows[12] = 50.0
    closes = _flat(n, 100.0)

    result = await find_support_resistance("TEST", _sr_json(highs, lows, closes))

    assert "error" not in result
    support_levels = [s["level"] for s in result["supports"]]
    assert 0.0 in support_levels and 50.0 in support_levels


# ---------------------------------------------------------------------------
# Helpers (unit contracts)
# ---------------------------------------------------------------------------


def test_dedupe_levels_merges_nearby_keeps_strongest():
    levels = [
        {"level": 100.0, "type": "support", "strength": 2},
        {"level": 100.5, "type": "support", "strength": 5},  # within 1% of 100
        {"level": 110.0, "type": "support", "strength": 1},  # far away
    ]

    merged = _dedupe_levels(levels)

    assert [l["level"] for l in merged] == [100.5, 110.0]  # strongest first


def test_dedupe_levels_empty():
    assert _dedupe_levels([]) == []


def test_nearest_level_below_and_above():
    levels = [{"level": 90.0, "strength": 1}, {"level": 95.0, "strength": 1}, {"level": 105.0, "strength": 1}]

    assert _nearest_level(100.0, levels, "below")["level"] == 95.0
    assert _nearest_level(100.0, levels, "above")["level"] == 105.0
    assert _nearest_level(100.0, [], "below") is None


# ---------------------------------------------------------------------------
# Aggregate exports (the registry shape agents consume)
# ---------------------------------------------------------------------------


def test_definitions_and_handlers_align():
    def_names = {d["function"]["name"] for d in TECHNICAL_TOOL_DEFINITIONS}
    handler_names = set(TECHNICAL_TOOL_HANDLERS)

    assert def_names == handler_names
    assert len(TECHNICAL_TOOL_DEFINITIONS) == 2
    for definition in TECHNICAL_TOOL_DEFINITIONS:
        fn = definition["function"]
        assert definition["type"] == "function"
        assert fn["description"]
        assert fn["parameters"]["type"] == "object"
        assert fn["parameters"]["required"]
