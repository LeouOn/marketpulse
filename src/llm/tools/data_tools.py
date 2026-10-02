"""Data Tools -- Market data fetching functions callable by LLM agents.

Each tool exports:
  - ``TOOL_DEFINITION`` -- OpenAI-compatible function definition dict
  - An async callable matching the tool name

Tool index
---------
===============  ==================================================
Tool Name         Wraps
===============  ==================================================
get_market_internals  MarketPulseCollector.collect_market_internals()
get_ohlcv             YahooFinanceClient.get_bars()
get_breadth           MarketBreadthCollector.get_market_internals()
get_symbol_52w_stats  Computed from YahooFinanceClient OHLCV data
===============  ==================================================
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger


def _num_or_none(value: Any) -> float | None:
    """Coerce to float; None/NaN/inf become ``None`` (JSON null).

    Tool payloads are JSON-serialized by the agent framework, where a stray
    ``nan`` float raises and a ``None`` cell crashes ``float()`` — a single bad
    cell must not kill the whole tool result.
    """
    try:
        f = float(value)
    except (TypeError, ValueError):
        return None
    return f if math.isfinite(f) else None


def _round_or_none(value: Any, digits: int = 4) -> float | None:
    n = _num_or_none(value)
    return None if n is None else round(n, digits)


def _int_or_none(value: Any) -> int | None:
    n = _num_or_none(value)
    return None if n is None else int(n)


def _na(value: Any) -> Any:
    """``"N/A"`` for missing AND present-but-None values (``dict.get``'s
    default does not cover the latter), preserving falsy-but-real 0/0.0."""
    return "N/A" if value is None else value


# ---------------------------------------------------------------------------
# Tool: get_market_internals
# ---------------------------------------------------------------------------

GET_MARKET_INTERNALS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_market_internals",
        "description": (
            "Fetch current real-time market internals for major indices and assets. "
            "Returns price, change, change_pct, and volume for SPY, QQQ, IWM, VIX, "
            "NQ futures, BTC-USD, ETH-USD, and macro indicators (DXY, gold, oil, yields). "
            "Use this to get a snapshot of current market conditions."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


async def get_market_internals() -> dict[str, Any]:
    """Fetch current market internals from the collector."""
    try:
        from src.data.market_collector import MarketPulseCollector

        collector = MarketPulseCollector()
        await collector.initialize()
        internals = await collector.collect_market_internals()

        if not internals:
            return {"error": "No market data available -- check data source connectivity"}

        # Trim to a manageable size for the LLM context
        summary: dict[str, Any] = {}
        key_symbols = ["spy", "qqq", "iwm", "vix", "nq=f", "btc-usd", "eth-usd"]
        for key in key_symbols:
            if key in internals:
                data = internals[key]
                if isinstance(data, dict):
                    summary[key] = {
                        "price": _na(data.get("price")),
                        "change": _na(data.get("change")),
                        "change_pct": _na(data.get("change_pct")),
                        "volume": _na(data.get("volume")),
                    }

        # Add macro if available
        if "macro" in internals:
            summary["macro"] = internals["macro"]

        summary["data_source"] = internals.get("data_source", "unknown")
        summary["timestamp"] = datetime.now().isoformat()

        return summary

    except Exception as e:
        logger.error(f"get_market_internals error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_ohlcv
# ---------------------------------------------------------------------------

GET_OHLCV_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_ohlcv",
        "description": (
            "Fetch historical OHLCV (Open, High, Low, Close, Volume) candlestick data "
            "for a given symbol. Returns the most recent candles as an array of "
            "{time, open, high, low, close, volume} objects. "
            "Valid periods: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max. "
            "Valid intervals: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1wk, 1mo."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol, e.g. SPY, AAPL, BTC-USD, NQ=F",
                },
                "period": {
                    "type": "string",
                    "description": "Lookback period: 1d, 5d, 1mo, 3mo, 6mo, 1y, 2y, 5y, max",
                },
                "interval": {
                    "type": "string",
                    "description": "Candle interval: 1m, 5m, 15m, 30m, 1h, 4h, 1d, 1wk, 1mo",
                },
            },
            "required": ["symbol"],
        },
    },
}


async def get_ohlcv(
    symbol: str,
    period: str = "1mo",
    interval: str = "1d",
) -> dict[str, Any]:
    """Fetch OHLCV data from Yahoo Finance."""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        # Strip $ prefix if present (breadth symbols use $SPY format)
        clean_symbol = symbol.lstrip("$")

        client = YahooFinanceClient()
        # get_bars is synchronous -- run in thread to avoid blocking
        df: pd.DataFrame | None = await asyncio.to_thread(client.get_bars, clean_symbol, period, interval)

        if df is None or df.empty:
            return {
                "error": (
                    f"No OHLCV data returned for {clean_symbol} "
                    f"({period}/{interval}). The symbol may be delisted, "
                    f"invalid, or yfinance is rate-limiting. Try a different "
                    f"symbol or a shorter period like '5d'."
                )
            }

        # Normalise yfinance MultiIndex columns: ('open','SPY') -> 'open'
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        # Build a compact candle list for the LLM context. Non-finite / missing
        # cells serialize as null instead of crashing (int(nan) raises) or
        # leaking nan floats into the agent's JSON.
        candles: list[dict[str, Any]] = []
        for idx, row in df.tail(50).iterrows():  # cap at 50 candles
            candles.append(
                {
                    "time": str(idx),
                    "open": _round_or_none(row.get("open")),
                    "high": _round_or_none(row.get("high")),
                    "low": _round_or_none(row.get("low")),
                    "close": _round_or_none(row.get("close")),
                    "volume": _int_or_none(row.get("volume")),
                }
            )

        return {
            "symbol": clean_symbol,
            "period": period,
            "interval": interval,
            "candles": candles,
            "count": len(candles),
            "latest_close": candles[-1]["close"] if candles else None,
        }

    except Exception as e:
        logger.error(f"get_ohlcv error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_breadth
# ---------------------------------------------------------------------------

GET_BREADTH_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_breadth",
        "description": (
            "Fetch market breadth indicators: advance/decline ratios for NYSE and Nasdaq, "
            "new 52-week highs/lows, TICK proxy, VOLD (volume delta), and "
            "McClellan Oscillator. Use this to assess broad market participation "
            "beyond just the major indices."
        ),
        "parameters": {
            "type": "object",
            "properties": {},
            "required": [],
        },
    },
}


async def get_breadth() -> dict[str, Any]:
    """Fetch breadth indicators."""
    try:
        from src.data.market_breadth import MarketBreadthCollector

        collector = MarketBreadthCollector()
        # get_market_internals is synchronous -- run in thread
        breadth = await asyncio.to_thread(collector.get_market_internals)

        if not breadth:
            return {"error": "No breadth data available"}

        # Pick the most relevant fields (present-but-None degrades to "N/A";
        # falsy-but-real values like 0 pass through).
        return {
            "nyse_advancing": _na(breadth.get("nyse_advancing")),
            "nyse_declining": _na(breadth.get("nyse_declining")),
            "nyse_ad_ratio": _na(breadth.get("nyse_ad_ratio")),
            "nasdaq_advancing": _na(breadth.get("nasdaq_advancing")),
            "nasdaq_declining": _na(breadth.get("nasdaq_declining")),
            "nasdaq_ad_ratio": _na(breadth.get("nasdaq_ad_ratio")),
            "new_highs_52w": _na(breadth.get("new_highs_52w")),
            "new_lows_52w": _na(breadth.get("new_lows_52w")),
            "mcclellan_osc": _na(breadth.get("mcclellan_osc")),
            "tick_avg": _na(breadth.get("tick_avg_30m")),
            "vold": _na(breadth.get("vold_nyse")),
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"get_breadth error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Tool: get_symbol_52w_stats
# ---------------------------------------------------------------------------

GET_52W_STATS_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "get_symbol_52w_stats",
        "description": (
            "Get 52-week high, 52-week low, current price, and percent distance "
            "from both extremes for a given symbol. Useful for assessing whether "
            "a symbol is near yearly highs or lows."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Ticker symbol, e.g. SPY, AAPL, BTC-USD",
                },
            },
            "required": ["symbol"],
        },
    },
}


async def get_symbol_52w_stats(symbol: str) -> dict[str, Any]:
    """Compute 52-week stats from Yahoo Finance OHLCV data."""
    try:
        from src.api.yahoo_client import YahooFinanceClient

        clean_symbol = symbol.lstrip("$")
        client = YahooFinanceClient()

        # Fetch 1 year of daily data
        df: pd.DataFrame | None = await asyncio.to_thread(client.get_bars, clean_symbol, "1y", "1d")

        if df is None or df.empty:
            return {"error": (f"No data for {clean_symbol}. yfinance may be rate-limiting or the symbol is invalid.")}

        # Normalise yfinance MultiIndex columns
        if isinstance(df.columns, pd.MultiIndex):
            df.columns = [c[0].lower() for c in df.columns]
        else:
            df.columns = [c.lower() for c in df.columns]

        # Verify required columns exist
        required = {"high", "low", "close"}
        missing = required - set(df.columns)
        if missing:
            return {
                "error": (f"Data for {clean_symbol} is missing columns: {missing}. Got columns: {list(df.columns)}")
            }

        high_52w = _num_or_none(df["high"].max())
        low_52w = _num_or_none(df["low"].min())
        current = _num_or_none(df["close"].iloc[-1])
        if high_52w is None or low_52w is None or current is None:
            return {
                "error": (
                    f"Data for {clean_symbol} contains non-finite high/low/close values; "
                    f"refusing to compute 52-week stats"
                )
            }

        # A zero reference makes the percentage undefined (and used to divide
        # by zero, killing the whole result); report null for that one field.
        pct_from_high = None if high_52w == 0 else round(((current - high_52w) / high_52w) * 100, 2)
        pct_from_low = None if low_52w == 0 else round(((current - low_52w) / low_52w) * 100, 2)

        # Find the date of the 52W high and low
        high_date = str(df["high"].idxmax())
        low_date = str(df["low"].idxmin())

        return {
            "symbol": clean_symbol,
            "current_price": current,
            "high_52w": high_52w,
            "low_52w": low_52w,
            "pct_from_52w_high": pct_from_high,
            "pct_from_52w_low": pct_from_low,
            "high_date": high_date,
            "low_date": low_date,
            "timestamp": datetime.now().isoformat(),
        }

    except Exception as e:
        logger.error(f"get_symbol_52w_stats error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

DATA_TOOL_DEFINITIONS: list[dict[str, Any]] = [
    GET_MARKET_INTERNALS_DEF,
    GET_OHLCV_DEF,
    GET_BREADTH_DEF,
    GET_52W_STATS_DEF,
]

DATA_TOOL_HANDLERS: dict[str, Any] = {
    "get_market_internals": get_market_internals,
    "get_ohlcv": get_ohlcv,
    "get_breadth": get_breadth,
    "get_symbol_52w_stats": get_symbol_52w_stats,
}
