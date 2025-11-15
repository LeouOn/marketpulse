"""
Trade Journal and Analytics

Track and analyze trading performance:
- Detailed trade logging
- Performance statistics
- Setup analysis (which ICT setups work best?)
- Session analysis (best trading times)
- Continuous improvement insights
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any, Tuple
from datetime import datetime, date, timedelta
from collections import defaultdict
import pandas as pd
import numpy as np
from loguru import logger

from src.state.position_manager import Position, PositionSide


@dataclass
class PerformanceStats:
    """Comprehensive performance statistics"""
    # Basic metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    break_even_trades: int

    # P&L metrics
    total_pnl: float
    gross_profit: float
    gross_loss: float
    average_win: float
    average_loss: float
    largest_win: float
    largest_loss: float

    # Ratios
    win_rate: float  # Percentage
    profit_factor: float  # Gross profit / Gross loss
    average_rr: float  # Average risk/reward achieved
    expectancy: float  # Expected value per trade

    # Risk metrics
    max_drawdown: float
    max_drawdown_pct: float
    sharpe_ratio: Optional[float] = None
    consecutive_wins: int = 0
    consecutive_losses: int = 0
    max_consecutive_wins: int = 0
    max_consecutive_losses: int = 0

    # Additional insights
    best_setup: Optional[str] = None
    worst_setup: Optional[str] = None
    best_session: Optional[str] = None
    worst_session: Optional[str] = None


@dataclass
class SetupAnalysis:
    """Analysis of specific setup type"""
    setup_type: str
    total_trades: int
    win_rate: float
    profit_factor: float
    total_pnl: float
    average_pnl: float
    best_trade: float
    worst_trade: float


@dataclass
class SessionAnalysis:
    """Analysis of trading session"""
    session: str
    total_trades: int
    win_rate: float
    total_pnl: float
    average_pnl: float


class TradeJournal:
    """
    Comprehensive trade journaling and analytics

    Features:
    - Detailed trade logging
    - Performance metrics
    - Setup effectiveness analysis
    - Best/worst trading times
    - Continuous improvement insights
    """

    def __init__(self):
        """Initialize trade journal"""
        self.trades: List[Position] = []
        logger.info("Trade Journal initialized")

    def add_trade(self, position: Position) -> None:
        """
        Log a completed trade

        Args:
            position: Closed position to log
        """
        if position.realized_pnl is None:
            logger.warning("Cannot log trade without realized P&L")
            return

        self.trades.append(position)
        logger.info(
            f"Trade logged: {position.symbol} {position.side.value} "
            f"P&L: ${position.realized_pnl:+.2f}"
        )

    def load_trades(self, positions: List[Position]) -> None:
        """
        Load multiple trades

        Args:
            positions: List of closed positions
        """
        self.trades = [p for p in positions if p.realized_pnl is not None]
        logger.info(f"Loaded {len(self.trades)} trades")

    def analyze_performance(
        self,
        days: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> PerformanceStats:
        """
        Calculate comprehensive performance statistics

        Args:
            days: Last N days (optional)
            start_date: Start date (optional)
            end_date: End date (optional)

        Returns:
            PerformanceStats object
        """
        # Filter trades by date range
        trades = self._filter_trades_by_date(days, start_date, end_date)

        if not trades:
            logger.warning("No trades found for analysis")
            return self._empty_stats()

        # Basic counts
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.realized_pnl > 0)
        losing_trades = sum(1 for t in trades if t.realized_pnl < 0)
        break_even_trades = sum(1 for t in trades if t.realized_pnl == 0)

        # P&L metrics
        pnls = [t.realized_pnl for t in trades]
        total_pnl = sum(pnls)
        wins = [p for p in pnls if p > 0]
        losses = [p for p in pnls if p < 0]

        gross_profit = sum(wins) if wins else 0
        gross_loss = abs(sum(losses)) if losses else 0
        average_win = np.mean(wins) if wins else 0
        average_loss = abs(np.mean(losses)) if losses else 0
        largest_win = max(wins) if wins else 0
        largest_loss = min(losses) if losses else 0

        # Ratios
        win_rate = (winning_trades / total_trades * 100) if total_trades > 0 else 0
        profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

        # Average R:R achieved
        rr_ratios = []
        for t in trades:
            if t.risk_amount and t.risk_amount > 0 and t.realized_pnl is not None:
                rr_ratios.append(abs(t.realized_pnl / t.risk_amount))

        average_rr = np.mean(rr_ratios) if rr_ratios else 0

        # Expectancy (average $ per trade)
        expectancy = total_pnl / total_trades if total_trades > 0 else 0

        # Drawdown
        max_dd, max_dd_pct = self._calculate_max_drawdown(trades)

        # Sharpe ratio
        sharpe = self._calculate_sharpe_ratio(pnls) if len(pnls) > 1 else None

        # Consecutive streaks
        consecutive = self._calculate_consecutive_streaks(trades)

        # Best/worst setups and sessions
        best_setup, worst_setup = self._find_best_worst_setups(trades)
        best_session, worst_session = self._find_best_worst_sessions(trades)

        return PerformanceStats(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            break_even_trades=break_even_trades,
            total_pnl=total_pnl,
            gross_profit=gross_profit,
            gross_loss=gross_loss,
            average_win=average_win,
            average_loss=average_loss,
            largest_win=largest_win,
            largest_loss=largest_loss,
            win_rate=win_rate,
            profit_factor=profit_factor,
            average_rr=average_rr,
            expectancy=expectancy,
            max_drawdown=max_dd,
            max_drawdown_pct=max_dd_pct,
            sharpe_ratio=sharpe,
            consecutive_wins=consecutive['current_wins'],
            consecutive_losses=consecutive['current_losses'],
            max_consecutive_wins=consecutive['max_wins'],
            max_consecutive_losses=consecutive['max_losses'],
            best_setup=best_setup,
            worst_setup=worst_setup,
            best_session=best_session,
            worst_session=worst_session
        )

    def analyze_by_setup(
        self,
        days: Optional[int] = None
    ) -> List[SetupAnalysis]:
        """
        Analyze performance by setup type

        Args:
            days: Last N days (optional)

        Returns:
            List of SetupAnalysis objects
        """
        trades = self._filter_trades_by_date(days=days)
        by_setup = defaultdict(list)

        for trade in trades:
            setup = trade.setup_type or "Unknown"
            by_setup[setup].append(trade)

        analyses = []
        for setup, setup_trades in by_setup.items():
            pnls = [t.realized_pnl for t in setup_trades]
            wins = [p for p in pnls if p > 0]
            losses = [p for p in pnls if p < 0]

            total_trades = len(setup_trades)
            win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

            gross_profit = sum(wins) if wins else 0
            gross_loss = abs(sum(losses)) if losses else 0
            profit_factor = (gross_profit / gross_loss) if gross_loss > 0 else float('inf') if gross_profit > 0 else 0

            analyses.append(SetupAnalysis(
                setup_type=setup,
                total_trades=total_trades,
                win_rate=win_rate,
                profit_factor=profit_factor,
                total_pnl=sum(pnls),
                average_pnl=np.mean(pnls),
                best_trade=max(pnls),
                worst_trade=min(pnls)
            ))

        # Sort by profit factor
        analyses.sort(key=lambda x: x.profit_factor, reverse=True)
        return analyses

    def analyze_by_session(
        self,
        days: Optional[int] = None
    ) -> List[SessionAnalysis]:
        """
        Analyze performance by trading session

        Args:
            days: Last N days (optional)

        Returns:
            List of SessionAnalysis objects
        """
        trades = self._filter_trades_by_date(days=days)
        by_session = defaultdict(list)

        for trade in trades:
            session = trade.session or "Unknown"
            by_session[session].append(trade)

        analyses = []
        for session, session_trades in by_session.items():
            pnls = [t.realized_pnl for t in session_trades]
            wins = [p for p in pnls if p > 0]

            total_trades = len(session_trades)
            win_rate = (len(wins) / total_trades * 100) if total_trades > 0 else 0

            analyses.append(SessionAnalysis(
                session=session,
                total_trades=total_trades,
                win_rate=win_rate,
                total_pnl=sum(pnls),
                average_pnl=np.mean(pnls)
            ))

        # Sort by total P&L
        analyses.sort(key=lambda x: x.total_pnl, reverse=True)
        return analyses

    def get_equity_curve(
        self,
        starting_balance: float = 10000
    ) -> pd.DataFrame:
        """
        Generate equity curve

        Args:
            starting_balance: Starting account balance

        Returns:
            DataFrame with timestamp and balance columns
        """
        if not self.trades:
            return pd.DataFrame(columns=['timestamp', 'balance'])

        # Sort trades by exit time
        sorted_trades = sorted(self.trades, key=lambda t: t.exit_timestamp)

        equity_data = []
        balance = starting_balance

        for trade in sorted_trades:
            balance += trade.realized_pnl
            equity_data.append({
                'timestamp': trade.exit_timestamp,
                'balance': balance,
                'pnl': trade.realized_pnl
            })

        return pd.DataFrame(equity_data)

    def get_insights(self, days: int = 30) -> Dict[str, Any]:
        """
        Get actionable trading insights

        Args:
            days: Last N days to analyze

        Returns:
            Dictionary of insights and recommendations
        """
        stats = self.analyze_performance(days=days)
        setup_analysis = self.analyze_by_setup(days=days)
        session_analysis = self.analyze_by_session(days=days)

        insights = {
            'summary': {
                'period_days': days,
                'total_trades': stats.total_trades,
                'win_rate': f"{stats.win_rate:.1f}%",
                'profit_factor': f"{stats.profit_factor:.2f}",
                'total_pnl': f"${stats.total_pnl:+,.2f}",
                'expectancy': f"${stats.expectancy:+.2f}"
            },
            'warnings': [],
            'recommendations': [],
            'strengths': []
        }

        # Warnings
        if stats.consecutive_losses >= 3:
            insights['warnings'].append(
                f"⚠️ {stats.consecutive_losses} consecutive losses. Take a break and review recent trades."
            )

        if stats.win_rate < 40:
            insights['warnings'].append(
                f"⚠️ Low win rate ({stats.win_rate:.1f}%). Review trade selection criteria."
            )

        if stats.profit_factor < 1.5:
            insights['warnings'].append(
                f"⚠️ Low profit factor ({stats.profit_factor:.2f}). Winners not big enough or losers too large."
            )

        if stats.average_rr < 1.0:
            insights['warnings'].append(
                f"⚠️ Average R:R ({stats.average_rr:.2f}) below 1:1. Cutting winners too early or letting losers run?"
            )

        # Recommendations
        if stats.best_setup:
            insights['recommendations'].append(
                f"✅ Focus on '{stats.best_setup}' setup - your best performer"
            )

        if stats.worst_setup and stats.worst_setup != "Unknown":
            insights['recommendations'].append(
                f"❌ Avoid or refine '{stats.worst_setup}' setup - underperforming"
            )

        if stats.worst_session and stats.worst_session != "Unknown":
            insights['recommendations'].append(
                f"⏰ Consider avoiding '{stats.worst_session}' session - negative results"
            )

        # Strengths
        if stats.win_rate > 50:
            insights['strengths'].append(
                f"🎯 Strong win rate: {stats.win_rate:.1f}%"
            )

        if stats.profit_factor > 2.0:
            insights['strengths'].append(
                f"💰 Excellent profit factor: {stats.profit_factor:.2f}"
            )

        if stats.average_rr > 1.5:
            insights['strengths'].append(
                f"📈 Good risk/reward management: {stats.average_rr:.2f}:1"
            )

        insights['setup_rankings'] = [
            {
                'setup': s.setup_type,
                'trades': s.total_trades,
                'win_rate': f"{s.win_rate:.1f}%",
                'pf': f"{s.profit_factor:.2f}",
                'pnl': f"${s.total_pnl:+,.2f}"
            }
            for s in setup_analysis[:5]  # Top 5
        ]

        return insights

    def _filter_trades_by_date(
        self,
        days: Optional[int] = None,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> List[Position]:
        """Filter trades by date range"""
        trades = self.trades

        if days is not None:
            cutoff = datetime.now() - timedelta(days=days)
            trades = [t for t in trades if t.exit_timestamp and t.exit_timestamp >= cutoff]

        if start_date is not None:
            trades = [t for t in trades if t.exit_timestamp and t.exit_timestamp.date() >= start_date]

        if end_date is not None:
            trades = [t for t in trades if t.exit_timestamp and t.exit_timestamp.date() <= end_date]

        return trades

    def _calculate_max_drawdown(self, trades: List[Position]) -> Tuple[float, float]:
        """Calculate maximum drawdown"""
        if not trades:
            return 0.0, 0.0

        sorted_trades = sorted(trades, key=lambda t: t.exit_timestamp)

        peak = 0
        max_dd = 0
        max_dd_pct = 0
        cumulative = 0

        for trade in sorted_trades:
            cumulative += trade.realized_pnl
            if cumulative > peak:
                peak = cumulative

            dd = peak - cumulative
            if dd > max_dd:
                max_dd = dd
                max_dd_pct = (dd / peak * 100) if peak > 0 else 0

        return max_dd, max_dd_pct

    def _calculate_sharpe_ratio(self, pnls: List[float]) -> float:
        """Calculate Sharpe ratio"""
        if len(pnls) < 2:
            return 0.0

        returns = np.array(pnls)
        if returns.std() == 0:
            return 0.0

        # Annualized Sharpe (assuming ~252 trading days)
        return (returns.mean() / returns.std()) * np.sqrt(252)

    def _calculate_consecutive_streaks(self, trades: List[Position]) -> Dict[str, int]:
        """Calculate consecutive win/loss streaks"""
        sorted_trades = sorted(trades, key=lambda t: t.exit_timestamp)

        current_wins = 0
        current_losses = 0
        max_wins = 0
        max_losses = 0

        for trade in sorted_trades:
            if trade.realized_pnl > 0:
                current_wins += 1
                current_losses = 0
                max_wins = max(max_wins, current_wins)
            elif trade.realized_pnl < 0:
                current_losses += 1
                current_wins = 0
                max_losses = max(max_losses, current_losses)

        return {
            'current_wins': current_wins,
            'current_losses': current_losses,
            'max_wins': max_wins,
            'max_losses': max_losses
        }

    def _find_best_worst_setups(self, trades: List[Position]) -> Tuple[Optional[str], Optional[str]]:
        """Find best and worst performing setup types"""
        by_setup = defaultdict(list)

        for trade in trades:
            setup = trade.setup_type
            if setup:
                by_setup[setup].append(trade.realized_pnl)

        if not by_setup:
            return None, None

        setup_pfs = {}
        for setup, pnls in by_setup.items():
            wins = sum(p for p in pnls if p > 0)
            losses = abs(sum(p for p in pnls if p < 0))
            pf = (wins / losses) if losses > 0 else float('inf') if wins > 0 else 0
            setup_pfs[setup] = pf

        best = max(setup_pfs.items(), key=lambda x: x[1])[0] if setup_pfs else None
        worst = min(setup_pfs.items(), key=lambda x: x[1])[0] if setup_pfs else None

        return best, worst

    def _find_best_worst_sessions(self, trades: List[Position]) -> Tuple[Optional[str], Optional[str]]:
        """Find best and worst trading sessions"""
        by_session = defaultdict(list)

        for trade in trades:
            session = trade.session
            if session:
                by_session[session].append(trade.realized_pnl)

        if not by_session:
            return None, None

        session_pnls = {session: sum(pnls) for session, pnls in by_session.items()}

        best = max(session_pnls.items(), key=lambda x: x[1])[0] if session_pnls else None
        worst = min(session_pnls.items(), key=lambda x: x[1])[0] if session_pnls else None

        return best, worst

    def _empty_stats(self) -> PerformanceStats:
        """Return empty stats"""
        return PerformanceStats(
            total_trades=0,
            winning_trades=0,
            losing_trades=0,
            break_even_trades=0,
            total_pnl=0,
            gross_profit=0,
            gross_loss=0,
            average_win=0,
            average_loss=0,
            largest_win=0,
            largest_loss=0,
            win_rate=0,
            profit_factor=0,
            average_rr=0,
            expectancy=0,
            max_drawdown=0,
            max_drawdown_pct=0
        )
