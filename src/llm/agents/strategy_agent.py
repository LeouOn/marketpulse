"""StrategyProposalAgent — Proposes trading strategies and backtests them.

Reads ICT signals and divergences from other agents, proposes a concrete
strategy with entry/exit rules, then calls run_backtest to validate it.
Reports whether the strategy is viable with performance metrics.
"""

from __future__ import annotations

from .base import MarketAgent


class StrategyProposalAgent(MarketAgent):
    """Agent that proposes and backtests trading strategies."""

    AGENT_NAME = "strategy_agent"
    CAPABILITY = "reasoning"
    MAX_TOKENS = 1000
    TEMPERATURE = 0.3
    MAX_TURNS = 6

    TOOL_NAMES = [
        "run_backtest",
        "generate_ict_signals",
        "detect_divergences",
        "calculate_risk_metrics",
    ]

    SYSTEM_PROMPT = """You are the Strategy Agent for a trading analysis system.

Your job: propose a concrete trading strategy based on current signals,
then VALIDATE it by running a backtest.

WORKFLOW:
1. **Read Signals** — Review the ICT signals and divergences from other
   agents (provided in context). What patterns are active?
2. **Propose Strategy** — Based on the signals, propose a specific strategy:
   - Entry conditions (e.g. "Enter long when FVG + CVD confirmation appears
     on the 15m chart, with RSI divergence bullish")
   - Exit conditions (e.g. "Exit at first take-profit level or when CVD
     slope turns bearish")
   - Stop placement (e.g. "Stop below recent swing low, min 1.5x ATR")
   - Position sizing (e.g. "1% risk per trade, 1 contract")
3. **Backtest** — Call run_backtest with a 3-6 month historical period
   to validate the strategy. Report:
   - Win rate, profit factor, Sharpe ratio, max drawdown
   - Total trades, average winner/loser
   - Is the strategy viable? (viable = Sharpe > 0.5, win rate > 40%,
     profit factor > 1.2, max DD < 20%)
4. **Verdict** — VIABLE (deploy with caution), NEEDS_REFINEMENT (adjust
   parameters), or NOT_VIABLE (fundamentally flawed). Give specific
   reasons based on the backtest metrics.

RULES:
- If backtest data is unavailable (e.g. live market hours, no historical
  data), propose the strategy with a note that backtesting is pending.
- Suggest at least one concrete parameter adjustment if the strategy
  needs refinement.
- Use calculate_risk_metrics to validate position sizing.

Be specific with numbers. Your output feeds into the synthesis engine."""
