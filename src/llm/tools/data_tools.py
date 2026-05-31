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
import json
from datetime import datetime
from typing import Any

import pandas as pd
from loguru import logger

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
                        "price": data.get("price", "N/A"),
                        "change": data.get("change", "N/A"),
                        "change_pct": data.get("change_pct", "N/A"),
                        "volume": data.get("volume", "N/A"),
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
        df: pd.DataFrame | None = await asyncio.to_thread(
            client.get_bars, clean_symbol, period, interval
        )

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

        # Build a compact candle list for the LLM context
        candles: list[dict[str, Any]] = []
        for idx, row in df.tail(50).iterrows():  # cap at 50 candles
            candles.append({
                "time": str(idx),
                "open": round(float(row.get("open", 0)), 4),
                "high": round(float(row.get("high", 0)), 4),
                "low": round(float(row.get("low", 0)), 4),
                "close": round(float(row.get("close", 0)), 4),
                "volume": int(row.get("volume", 0)),
            })

        return {
            "symbol": symbol,
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

        # Pick the most relevant fields
        return {
            "nyse_advancing": breadth.get("nyse_advancing", "N/A"),
            "nyse_declining": breadth.get("nyse_declining", "N/A"),
            "nyse_ad_ratio": breadth.get("nyse_ad_ratio", "N/A"),
            "nasdaq_advancing": breadth.get("nasdaq_advancing", "N/A"),
            "nasdaq_declining": breadth.get("nasdaq_declining", "N/A"),
            "nasdaq_ad_ratio": breadth.get("nasdaq_ad_ratio", "N/A"),
            "new_highs_52w": breadth.get("new_highs_52w", "N/A"),
            "new_lows_52w": breadth.get("new_lows_52w", "N/A"),
            "mcclellan_osc": breadth.get("mcclellan_osc", "N/A"),
            "tick_avg": breadth.get("tick_avg_30m", "N/A"),
            "vold": breadth.get("vold_nyse", "N/A"),
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
        df: pd.DataFrame | None = await asyncio.to_thread(
            client.get_bars, clean_symbol, "1y", "1d"
        )

        if df is None or df.empty:
            return {
                "error": (
                    f"No data for {clean_symbol}. yfinance may be "
                    f"rate-limiting or the symbol is invalid."
                )
            }

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
                "error": (
                    f"Data for {clean_symbol} is missing columns: {missing}. "
                    f"Got columns: {list(df.columns)}"
                )
            }

        high_52w = float(df["high"].max())
        low_52w = float(df["low"].min())
        current = float(df["close"].iloc[-1])

        pct_from_high = round(((current - high_52w) / high_52w) * 100, 2)
        pct_from_low = round(((current - low_52w) / low_52w) * 100, 2)

        # Find the date of the 52W high and low
        high_date = str(df["high"].idxmax())
        low_date = str(df["low"].idxmin())

        return {
            "symbol": symbol,
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
