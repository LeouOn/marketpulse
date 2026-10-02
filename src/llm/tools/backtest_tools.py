"""Backtest Tools — Strategy backtesting functions callable by LLM agents.

Wraps BacktestEngine.run_backtest() for strategy validation.
"""

from __future__ import annotations

import asyncio
import math
from datetime import datetime
from typing import Any

from loguru import logger

# The metric fields the tool reports, in report order.
_METRIC_FIELDS = (
    "total_trades",
    "winning_trades",
    "losing_trades",
    "win_rate",
    "total_pnl",
    "total_pnl_percent",
    "profit_factor",
    "max_drawdown",
    "max_drawdown_percent",
    "sharpe_ratio",
    "average_winner",
    "average_loser",
    "expectancy",
    "fvg_success_rate",
    "divergence_success_rate",
)


def _metric(result: Any, name: str) -> Any:
    """One backtest metric as a JSON-clean value.

    The engine computes over pandas frames, so scalars can come back as numpy
    types (not JSON-serialisable) or as NaN/inf (e.g. sharpe with zero
    variance, profit_factor with no losers); a missing field (engine version
    skew) degrades to None instead of failing the whole tool.
    """
    value = getattr(result, name, None)
    if value is None:
        return None
    if hasattr(value, "item"):  # numpy scalar -> native Python scalar
        value = value.item()
    if isinstance(value, int) and not isinstance(value, bool):
        return value
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return round(value, 2) if math.isfinite(value) else None


# ---------------------------------------------------------------------------
# Tool: run_backtest
# ---------------------------------------------------------------------------

RUN_BACKTEST_DEF: dict[str, Any] = {
    "type": "function",
    "function": {
        "name": "run_backtest",
        "description": (
            "Run a historical backtest for a trading strategy on a given symbol. "
            "Returns comprehensive metrics: total trades, win rate, total P&L, "
            "profit factor, max drawdown, Sharpe ratio, average winner/loser, etc. "
            "Use this to validate a proposed strategy before deploying it live."
        ),
        "parameters": {
            "type": "object",
            "properties": {
                "symbol": {
                    "type": "string",
                    "description": "Symbol to backtest, e.g. SPY, NQ=F, BTC-USD",
                },
                "start_date": {
                    "type": "string",
                    "description": "Start date YYYY-MM-DD, e.g. 2024-01-01",
                },
                "end_date": {
                    "type": "string",
                    "description": "End date YYYY-MM-DD, e.g. 2024-12-31",
                },
                "initial_capital": {
                    "type": "number",
                    "description": "Starting capital in dollars (default 10000)",
                },
                "interval": {
                    "type": "string",
                    "description": "Candle interval: 5m, 15m, 1h, 1d (default 5m)",
                },
            },
            "required": ["symbol", "start_date", "end_date"],
        },
    },
}


async def run_backtest(
    symbol: str,
    start_date: str,
    end_date: str,
    initial_capital: float = 10000,
    interval: str = "5m",
) -> dict[str, Any]:
    """Run backtest on historical data."""
    try:
        from src.backtesting.backtest_engine import BacktestEngine

        engine = BacktestEngine()
        result = await asyncio.to_thread(
            engine.run_backtest,
            symbol=symbol,
            start_date=start_date,
            end_date=end_date,
            initial_capital=initial_capital,
            interval=interval,
        )

        return {
            "symbol": symbol,
            "period": f"{start_date} to {end_date}",
            "interval": interval,
            "initial_capital": initial_capital,
            "metrics": {name: _metric(result, name) for name in _METRIC_FIELDS},
            "timestamp": datetime.now().isoformat(),
        }
    except Exception as e:
        logger.error(f"run_backtest error: {e}")
        return {"error": str(e)}


# ---------------------------------------------------------------------------
# Aggregate exports
# ---------------------------------------------------------------------------

BACKTEST_TOOL_DEFINITIONS: list[dict[str, Any]] = [RUN_BACKTEST_DEF]
BACKTEST_TOOL_HANDLERS: dict[str, Any] = {"run_backtest": run_backtest}
