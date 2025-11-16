"""
Backtesting Engine Module

Validate trading strategies on historical data
with comprehensive performance analytics.
"""

from .backtest_engine import BacktestEngine, BacktestResults, Account, Trade

__all__ = ['BacktestEngine', 'BacktestResults', 'Account', 'Trade']
