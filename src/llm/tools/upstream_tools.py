"""Upstream Tools — Wraps the upstream analysis modules for LLM agents.

Each tool wraps a function from the upstream quant toolkit (ICT, order flow,
divergence, options, risk, indicators, regime, backtesting).
"""

from __future__ import annotations

import asyncio
import json
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger


# ---------------------------------------------------------------------------
# Tool: detect_divergences
# ---------------------------------------------------------------------------

DETECT_DIVERGENCES_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "detect_divergences",
        "description": (
            "Detect RSI, MACD, Stochastic, and Volume (OBV) divergences from "
            "OHLCV candle data. Returns regular (reversal) and hidden "
            "(continuation) divergences with strength scores. "
            "Provide the raw JSON output from get_ohlcv."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "ohlcv_json": {"type": "string", "description": "JSON from get_ohlcv"},
            },
            "required": ["symbol", "ohlcv_json"],
        },
    },
}


async def detect_divergences(symbol: str, ohlcv_json: str) -> dict[str, Any]:
    """Detect divergences from OHLCV data."""
    try:
        from src.analysis.divergence_detector import scan_for_divergences

        data = json.loads(ohlcv_json)
        candles = data.get("candles", [])
        if len(candles) < 30:
            return {"error": f"Need >=30 candles, got {len(candles)}"}

        df = pd.DataFrame(candles)
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)
                break

        result = await asyncio.to_thread(scan_for_divergences, df, 60.0)

        return {
            "symbol": symbol,
            "divergences_found": result.get("total_divergences", 0),
            "regular_bullish": result.get("regular_bullish", 0),
            "regular_bearish": result.get("regular_bearish", 0),
            "hidden_bullish": result.get("hidden_bullish", 0),
            "hidden_bearish": result.get("hidden_bearish", 0),
            "details": result.get("divergences", [])[:10],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"detect_divergences error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: generate_ict_signals
# ---------------------------------------------------------------------------

GENERATE_ICT_SIGNALS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "generate_ict_signals",
        "description": (
            "Generate ICT/SMC (Smart Money Concepts) trading signals from "
            "OHLCV data. Detects FVG + CVD confirmations, Order Block retests, "
            "Liquidity Sweeps with reversals, and Market Structure Breaks. "
            "Returns signals with entry, stop, targets, confidence, and R:R."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "ohlcv_json": {"type": "string", "description": "JSON from get_ohlcv"},
            },
            "required": ["symbol", "ohlcv_json"],
        },
    },
}


async def generate_ict_signals(symbol: str, ohlcv_json: str) -> dict[str, Any]:
    """Generate ICT/SMC trading signals."""
    try:
        from src.analysis.ict_signal_generator import ICTSignalGenerator

        data = json.loads(ohlcv_json)
        candles = data.get("candles", [])
        if len(candles) < 20:
            return {"error": f"Need >=20 candles, got {len(candles)}"}

        df = pd.DataFrame(candles)
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)
                break

        generator = ICTSignalGenerator()
        result = await asyncio.to_thread(generator.generate_signals, df, None)

        signals = result.get("signals", [])
        return {
            "symbol": symbol,
            "signal_count": len(signals),
            "signals": [
                {
                    "type": s.get("type", s.type if hasattr(s, "type") else "unknown"),
                    "confidence": s.get("confidence", 0),
                    "entry": s.get("entry_price", 0),
                    "stop": s.get("stop_loss", 0),
                    "targets": s.get("take_profit", s.get("targets", [])),
                    "trigger": str(s.get("trigger", ""))[:120],
                    "rr_ratio": s.get("risk_reward_ratio", 0),
                }
                for s in signals[:5]
            ],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"generate_ict_signals error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: compute_indicators
# ---------------------------------------------------------------------------

COMPUTE_INDICATORS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "compute_indicators",
        "description": (
            "Compute common technical indicators from OHLCV data: "
            "SMA(20/50/200), EMA(20), RSI(14), MACD, Bollinger Bands, ATR(14). "
            "Returns current values and basic signals (overbought/oversold, etc.)."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "ohlcv_json": {"type": "string", "description": "JSON from get_ohlcv"},
            },
            "required": ["symbol", "ohlcv_json"],
        },
    },
}


async def compute_indicators(symbol: str, ohlcv_json: str) -> dict[str, Any]:
    """Compute technical indicators."""
    try:
        from src.analysis.technical_indicators import TechnicalIndicators

        data = json.loads(ohlcv_json)
        candles = data.get("candles", [])
        if len(candles) < 20:
            return {"error": f"Need >=20 candles, got {len(candles)}"}

        df = pd.DataFrame(candles)
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)
                break

        ti = TechnicalIndicators()
        result = await asyncio.to_thread(ti.compute_all, df) if hasattr(ti, "compute_all") else {}

        # Fallback: call individual methods
        if not result:
            result = {
                "sma_20": await asyncio.to_thread(ti.sma, df["close"], 20) if hasattr(ti, "sma") else None,
                "sma_50": await asyncio.to_thread(ti.sma, df["close"], 50) if hasattr(ti, "sma") else None,
                "rsi": await asyncio.to_thread(ti.rsi, df["close"]) if hasattr(ti, "rsi") else None,
                "macd": await asyncio.to_thread(ti.macd, df["close"]) if hasattr(ti, "macd") else None,
                "atr": await asyncio.to_thread(ti.atr, df) if hasattr(ti, "atr") else None,
            }

        # Extract latest values
        def _last(v):
            if v is None:
                return None
            if hasattr(v, "iloc"):
                return round(float(v.iloc[-1]), 4) if len(v) > 0 else None
            return round(float(v), 4)

        return {
            "symbol": symbol,
            "indicators": {k: _last(v) for k, v in result.items() if v is not None},
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"compute_indicators error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: classify_regime
# ---------------------------------------------------------------------------

CLASSIFY_REGIME_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "classify_regime",
        "description": (
            "Classify the current market regime: TRENDING_BULLISH, "
            "TRENDING_BEARISH, RANGE_BOUND, CHOPPY_AVOID, or BREAKOUT_PENDING. "
            "Uses price action, VIX level, ATR, and volume context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "current_price": {"type": "number"},
                "vix": {"type": "number", "description": "Current VIX level"},
                "atr": {"type": "number", "description": "Current ATR value"},
                "volume": {"type": "integer", "description": "Current volume"},
                "avg_volume": {"type": "integer", "description": "Average volume (20-day)"},
            },
            "required": ["symbol", "current_price", "vix", "atr"],
        },
    },
}


async def classify_regime(
    symbol: str, current_price: float, vix: float, atr: float,
    volume: int = 0, avg_volume: int = 0,
) -> dict[str, Any]:
    """Classify market regime."""
    try:
        # Heuristic regime classification (no LLM dependency)
        range_pct = (atr / current_price) * 100 if current_price > 0 else 0

        if vix > 25:
            regime = "CHOPPY_AVOID" if range_pct > 2 else "TRENDING_BEARISH"
        elif vix < 15:
            regime = "TRENDING_BULLISH" if range_pct < 1.5 else "RANGE_BOUND"
        elif range_pct > 2.5:
            regime = "CHOPPY_AVOID"
        elif volume > avg_volume * 1.5 and avg_volume > 0:
            regime = "BREAKOUT_PENDING"
        else:
            regime = "RANGE_BOUND"

        return {
            "symbol": symbol,
            "regime": regime,
            "vix_level": vix,
            "atr_pct": round(range_pct, 2),
            "volume_ratio": round(volume / avg_volume, 2) if avg_volume > 0 else None,
            "description": {
                "TRENDING_BULLISH": "Strong uptrend — favor longs, trend-following strategies",
                "TRENDING_BEARISH": "Strong downtrend — favor shorts or cash",
                "RANGE_BOUND": "Sideways — trade both directions at boundaries",
                "CHOPPY_AVOID": "High volatility, low follow-through — reduce size or stay out",
                "BREAKOUT_PENDING": "Coiling/compression — wait for direction, then jump on",
            }.get(regime, ""),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"classify_regime error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: calculate_risk_metrics
# ---------------------------------------------------------------------------

CALCULATE_RISK_METRICS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "calculate_risk_metrics",
        "description": (
            "Calculate position sizing and risk metrics. Given entry, stop, "
            "account size, and risk %, returns suggested position size, "
            "risk amount, and R:R context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "entry_price": {"type": "number", "description": "Planned entry price"},
                "stop_loss": {"type": "number", "description": "Stop loss price"},
                "account_size": {"type": "number", "description": "Account size in dollars (default 25000)"},
                "risk_percent": {"type": "number", "description": "Risk per trade as % of account (default 1.0)"},
            },
            "required": ["entry_price", "stop_loss"],
        },
    },
}


async def calculate_risk_metrics(
    entry_price: float, stop_loss: float,
    account_size: float = 25000, risk_percent: float = 1.0,
) -> dict[str, Any]:
    """Calculate position sizing and risk metrics."""
    try:
        risk_per_share = abs(entry_price - stop_loss)
        if risk_per_share == 0:
            return {"error": "Entry and stop are the same price — invalid"}

        risk_amount = account_size * (risk_percent / 100)
        position_size = int(risk_amount / risk_per_share)
        total_position_value = position_size * entry_price

        return {
            "entry_price": entry_price,
            "stop_loss": stop_loss,
            "risk_per_share": round(risk_per_share, 2),
            "account_size": account_size,
            "risk_percent": risk_percent,
            "risk_amount": round(risk_amount, 2),
            "position_size_shares": position_size,
            "total_position_value": round(total_position_value, 2),
            "leverage": round(total_position_value / account_size, 2) if account_size > 0 else 0,
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"calculate_risk_metrics error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: screen_options_flow
# ---------------------------------------------------------------------------

SCREEN_OPTIONS_FLOW_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "screen_options_flow",
        "description": (
            "Screen for unusual options activity. Returns top opportunities "
            "with strategy preference (directional, premium_selling, neutral). "
            "Note: requires live market data — may return empty if market closed."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbols": {
                    "type": "string",
                    "description": "Comma-separated symbols, e.g. 'SPY,QQQ,AAPL'",
                },
                "strategy": {
                    "type": "string",
                    "description": "Strategy preference: directional, premium_selling, neutral",
                },
            },
            "required": ["symbols"],
        },
    },
}


async def screen_options_flow(
    symbols: str, strategy: str = "directional",
) -> dict[str, Any]:
    """Screen for unusual options activity."""
    try:
        from src.analysis.options_screener import OptionsScreener

        sym_list = [s.strip() for s in symbols.split(",") if s.strip()]
        screener = OptionsScreener()

        result = await asyncio.to_thread(
            screener.screen_with_macro_filter, sym_list, strategy or None
        )

        return {
            "symbols_screened": sym_list,
            "strategy": strategy,
            "opportunities": [
                {
                    "symbol": getattr(o, "symbol", str(o)),
                    "strike": getattr(o, "strike", 0),
                    "expiry": str(getattr(o, "expiry", "")),
                    "type": getattr(o, "option_type", ""),
                    "premium": getattr(o, "premium", 0),
                    "volume": getattr(o, "volume", 0),
                    "open_interest": getattr(o, "open_interest", 0),
                }
                for o in (result if isinstance(result, list) else [])[:10]
            ],
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"screen_options_flow error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: analyze_order_flow
# ---------------------------------------------------------------------------

ANALYZE_ORDER_FLOW_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "analyze_order_flow",
        "description": (
            "Analyze order flow from OHLCV data: Cumulative Volume Delta (CVD) "
            "slope, delta divergence, absorption signals, and imbalance detection. "
            "Use for institutional order flow context."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {"type": "string", "description": "Ticker symbol"},
                "ohlcv_json": {"type": "string", "description": "JSON from get_ohlcv"},
            },
            "required": ["symbol", "ohlcv_json"],
        },
    },
}


async def analyze_order_flow(symbol: str, ohlcv_json: str) -> dict[str, Any]:
    """Analyze order flow from OHLCV data."""
    try:
        data = json.loads(ohlcv_json)
        candles = data.get("candles", [])
        if len(candles) < 10:
            return {"error": f"Need >=10 candles, got {len(candles)}"}

        df = pd.DataFrame(candles)
        for col in ["open", "high", "low", "close", "volume"]:
            if col not in df.columns:
                df.rename(columns={c: c.lower() for c in df.columns}, inplace=True)
                break

        # Simple order flow heuristics
        closes = df["close"].values
        volumes = df["volume"].values
        price_changes = closes[1:] - closes[:-1]

        # CVD proxy: cumulative (close - open) * volume
        cv_delta = ((df["close"] - df["open"]) * df["volume"]).sum()
        cvd_slope = "bullish" if cv_delta > 0 else "bearish"

        # Volume trend
        vol_trend = "increasing" if len(volumes) >= 5 and volumes[-5:].mean() > volumes[:5].mean() else "stable"

        # Absorption: high volume, small price change
        recent_range = abs(closes[-1] - closes[-5]) if len(closes) >= 5 else 0
        recent_vol = volumes[-5:].mean() if len(volumes) >= 5 else 0
        absorption = recent_vol > volumes.mean() * 1.5 and recent_range < (df["high"].max() - df["low"].min()) * 0.3

        return {
            "symbol": symbol,
            "cvd_slope": cvd_slope,
            "cumulative_delta": round(float(cv_delta), 0),
            "volume_trend": vol_trend,
            "absorption_detected": absorption,
            "candles_analyzed": len(candles),
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"analyze_order_flow error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

UPSTREAM_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    DETECT_DIVERGENCES_DEF,
    GENERATE_ICT_SIGNALS_DEF,
    COMPUTE_INDICATORS_DEF,
    CLASSIFY_REGIME_DEF,
    CALCULATE_RISK_METRICS_DEF,
    SCREEN_OPTIONS_FLOW_DEF,
    ANALYZE_ORDER_FLOW_DEF,
]

UPSTREAM_TOOL_HANDLERS: dict[str, Any] = {
    "detect_divergences": detect_divergences,
    "generate_ict_signals": generate_ict_signals,
    "compute_indicators": compute_indicators,
    "classify_regime": classify_regime,
    "calculate_risk_metrics": calculate_risk_metrics,
    "screen_options_flow": screen_options_flow,
    "analyze_order_flow": analyze_order_flow,
}
