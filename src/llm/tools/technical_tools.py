"""Technical Analysis Tools -- OHLCV analysis functions callable by LLM agents.

Each tool wraps ``OHLCAnalyzer`` methods.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

# ---------------------------------------------------------------------------
# Tool: analyze_symbol_technicals
# ---------------------------------------------------------------------------

ANALYZE_SYMBOL_TECHNICALS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "analyze_symbol_technicals",
        "description": (
            "Run comprehensive multi-timeframe technical analysis on a symbol. "
            "Returns trend direction, strength score, key support/resistance levels, "
            "detected candlestick patterns, and trading signals. "
            "You must provide OHLCV data from get_ohlcv first."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol, e.g. SPY, AAPL, BTC-USD",
                },
                "ohlcv_json": {
                    "type": "string",
                    "description": (
                        "JSON string of the OHLCV data returned by get_ohlcv. "
                        "Pass the raw JSON output from that tool."
                    ),
                },
            },
            "required": ["symbol", "ohlcv_json"],
        },
    },
}


async def analyze_symbol_technicals(symbol: str, ohlcv_json: str) -> dict[str, Any]:
    """Run multi-timeframe technical analysis on a symbol."""
    try:
        import json

        from src.analysis.ohlc_analyzer import OHLCAnalyzer

        ohlcv_data = json.loads(ohlcv_json)

        # Guard against LLM fabricating non-dict data (e.g. JSON array)
        if not isinstance(ohlcv_data, dict):
            return {
                "error": (
                    f"Invalid OHLCV data format: expected a JSON object, "
                    f"got {type(ohlcv_data).__name__}. Use the raw JSON "
                    f"returned by get_ohlcv -- do not fabricate data."
                )
            }

        # Format data for the analyzer -- it expects {"historical_data": {tf: {...}}}
        # Our get_ohlcv returns {"candles": [...]} -- wrap it
        candles = ohlcv_data.get("candles", [])
        interval = ohlcv_data.get("interval", "1d")

        wrapped: dict[str, Any] = {"historical_data": {}}
        wrapped["historical_data"][interval] = {
            "symbol": symbol,
            "data": candles,
        }

        analyzer = OHLCAnalyzer()
        result = analyzer.analyze_symbol(wrapped, symbol)

        # Trim for LLM context
        return {
            "symbol": result.get("symbol", symbol),
            "overall_trend": result.get("overall_trend", "NEUTRAL"),
            "overall_strength": result.get("overall_strength", 0),
            "key_levels": result.get("key_levels", {}),
            "patterns": result.get("patterns", [])[:10],
            "signals": result.get("signals", [])[:10],
            "timeframe_count": len(result.get("timeframes", {})),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"analyze_symbol_technicals error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: find_support_resistance
# ---------------------------------------------------------------------------

FIND_SUPPORT_RESISTANCE_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "find_support_resistance",
        "description": (
            "Identify key support and resistance levels for a symbol from "
            "OHLCV candle data. Returns levels with strength scores. "
            "Provide the raw JSON output from get_ohlcv."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol",
                },
                "ohlcv_json": {
                    "type": "string",
                    "description": "JSON string of OHLCV data from get_ohlcv",
                },
            },
            "required": ["symbol", "ohlcv_json"],
        },
    },
}


async def find_support_resistance(symbol: str, ohlcv_json: str) -> dict[str, Any]:
    """Find support and resistance levels from OHLCV data."""
    try:
        import json

        import numpy as np
        import pandas as pd

        ohlcv_data = json.loads(ohlcv_json)
        candles = ohlcv_data.get("candles", [])

        if len(candles) < 10:
            return {"error": f"Need at least 10 candles, got {len(candles)}"}

        df = pd.DataFrame(candles)
        df.columns = [c.lower() for c in df.columns]

        highs = df["high"].values
        lows = df["low"].values
        closes = df["close"].values

        # Simple pivot-based S/R detection
        supports: list[dict[str, Any]] = []
        resistances: list[dict[str, Any]] = []

        for i in range(2, len(df) - 2):
            # Resistance (pivot high)
            if highs[i] > highs[i - 1] and highs[i] > highs[i - 2] and highs[i] > highs[i + 1] and highs[i] > highs[i + 2]:
                resistances.append({
                    "level": round(float(highs[i]), 4),
                    "type": "resistance",
                    "strength": _level_touch_count(highs[i], highs, tolerance_pct=0.5),
                })
            # Support (pivot low)
            if lows[i] < lows[i - 1] and lows[i] < lows[i - 2] and lows[i] < lows[i + 1] and lows[i] < lows[i + 2]:
                supports.append({
                    "level": round(float(lows[i]), 4),
                    "type": "support",
                    "strength": _level_touch_count(lows[i], lows, tolerance_pct=0.5),
                })

        # Sort by strength, deduplicate nearby levels
        supports = _dedupe_levels(supports)
        resistances = _dedupe_levels(resistances)

        current_price = float(closes[-1])

        return {
            "symbol": symbol,
            "current_price": current_price,
            "supports": supports[:5],
            "resistances": resistances[:5],
            "nearest_support": _nearest_level(current_price, supports, "below"),
            "nearest_resistance": _nearest_level(current_price, resistances, "above"),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"find_support_resistance error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _level_touch_count(level: float, prices: "np.ndarray", tolerance_pct: float = 0.5) -> int:
    """Count how many times price touched within tolerance_pct of a level."""
    tolerance = level * tolerance_pct / 100.0
    return int(((prices >= level - tolerance) & (prices <= level + tolerance)).sum())


def _dedupe_levels(levels: list[dict], min_distance_pct: float = 1.0) -> list[dict]:
    """Merge nearby levels, keeping the strongest."""
    if not levels:
        return []
    sorted_levels = sorted(levels, key=lambda x: x["level"])
    merged: list[dict] = []
    for lvl in sorted_levels:
        if not merged:
            merged.append(lvl)
            continue
        last = merged[-1]
        if abs(lvl["level"] - last["level"]) / last["level"] * 100 < min_distance_pct:
            # Merge -- keep the stronger one
            if lvl["strength"] > last["strength"]:
                merged[-1] = lvl
        else:
            merged.append(lvl)
    return sorted(merged, key=lambda x: x["strength"], reverse=True)


def _nearest_level(price: float, levels: list[dict], direction: str) -> dict | None:
    """Find nearest support (below) or resistance (above)."""
    if not levels:
        return None
    if direction == "below":
        candidates = [l for l in levels if l["level"] < price]
        return min(candidates, key=lambda x: price - x["level"]) if candidates else None
    else:
        candidates = [l for l in levels if l["level"] > price]
        return min(candidates, key=lambda x: x["level"] - price) if candidates else None


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

TECHNICAL_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    ANALYZE_SYMBOL_TECHNICALS_DEF,
    FIND_SUPPORT_RESISTANCE_DEF,
]

TECHNICAL_TOOL_HANDLERS: dict[str, Any] = {
    "analyze_symbol_technicals": analyze_symbol_technicals,
    "find_support_resistance": find_support_resistance,
}
