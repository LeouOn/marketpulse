"""
Backtesting Engine Module

Validate trading strategies on historical data
with comprehensive performance analytics.
"""

from .backtest_engine import Account, BacktestEngine, BacktestResults, Trade

__all__ = ["BacktestEngine", "BacktestResults", "Account", "Trade"]
