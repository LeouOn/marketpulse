"""
AI Trading Analyst Module

Combines Massive.com data + Claude 4 + MarketPulse analysis
for intelligent market insights and trade recommendations.
"""

from .massive_analyst import MassiveAIAnalyst, TradingContext

__all__ = ['MassiveAIAnalyst', 'TradingContext']
