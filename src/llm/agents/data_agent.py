"""DataAgent -- Fetches market data via tools.

Responsible for: market internals, OHLCV data, breadth indicators, 52-week stats.
Does NOT perform technical analysis -- that's TechnicalAgent's job.
"""

from __future__ import annotations

from .base import MarketAgent


class DataAgent(MarketAgent):
    """Agent that fetches market data."""

    AGENT_NAME = "data_agent"
    CAPABILITY = "fast"         # Data fetching is simple lookups
    MAX_TOKENS = 600
    TEMPERATURE = 0.2

    TOOL_NAMES = [
        "get_market_internals",
        "get_ohlcv",
        "get_breadth",
        "get_symbol_52w_stats",
    ]

    SYSTEM_PROMPT = """You are the Data Agent for a trading analysis system.

Your job is to fetch market data that other agents or the orchestrator need
for analysis.  You do NOT interpret the data -- just retrieve it.

RULES:
1. When asked to fetch data, use the appropriate tool immediately.
2. If multiple data points are needed (e.g. internals + OHLCV for SPY),
   call all relevant tools in sequence.
3. After fetching, summarise WHAT you retrieved (symbols, date ranges,
   key numbers like price/change) in 2-3 sentences.
4. Always include the raw tool output so downstream agents can use it.
5. If a tool returns an error, report it clearly and suggest alternatives.

Be concise.  Your output will be consumed by other agents."""
