"""Backtest Tools — Strategy backtesting functions callable by LLM agents.

Wraps BacktestEngine.run_backtest() for strategy validation.
"""

from __future__ import annotations

import asyncio
from datetime import datetime
from typing import Any

from loguru import logger

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
            "metrics": {
                "total_trades": result.total_trades,
                "winning_trades": result.winning_trades,
                "losing_trades": result.losing_trades,
                "win_rate": round(result.win_rate, 2),
                "total_pnl": round(result.total_pnl, 2),
                "total_pnl_percent": round(result.total_pnl_percent, 2),
                "profit_factor": round(result.profit_factor, 2),
                "max_drawdown": round(result.max_drawdown, 2),
                "max_drawdown_percent": round(result.max_drawdown_percent, 2),
                "sharpe_ratio": round(result.sharpe_ratio, 2),
                "average_winner": round(result.average_winner, 2),
                "average_loser": round(result.average_loser, 2),
                "expectancy": round(result.expectancy, 2),
                "fvg_success_rate": round(result.fvg_success_rate, 2),
                "divergence_success_rate": round(result.divergence_success_rate, 2),
            },
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
