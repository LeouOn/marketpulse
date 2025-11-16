"""
Test Backtesting Engine

Tests for backtest engine, position scaler, and regime classifier.
"""

import pytest
import pandas as pd
import numpy as np
from datetime import datetime, timedelta

from src.backtesting.backtest_engine import BacktestEngine, Trade, Account
from src.analysis.position_scaler import PositionScaler, calculate_performance_stats


class TestBacktestEngine:
    """Test backtesting functionality"""

    def test_engine_initialization(self):
        """Test engine can be initialized"""
        engine = BacktestEngine()
        assert engine is not None
        assert engine.ict_analyzer is not None
        assert engine.signal_generator is not None

    def test_account(self):
        """Test simulated account"""
        account = Account(initial_capital=10000)

        assert account.balance == 10000
        assert account.max_drawdown == 0.0

        # Simulate winning trade
        trade = Trade(
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            entry_price=100.0,
            exit_price=102.0,
            direction="LONG",
            contracts=1,
            pnl=200.0,
            pnl_percent=2.0,
            duration_minutes=30,
            setup_type="TEST",
            win=True
        )

        account.update(trade)
        assert account.balance == 10200

        # Simulate losing trade
        trade_loss = Trade(
            entry_time=datetime.now(),
            exit_time=datetime.now(),
            entry_price=102.0,
            exit_price=100.0,
            direction="SHORT",
            contracts=1,
            pnl=-200.0,
            pnl_percent=-2.0,
            duration_minutes=30,
            setup_type="TEST",
            win=False
        )

        account.update(trade_loss)
        assert account.balance == 10000

    def test_trade_dataclass(self):
        """Test Trade dataclass"""
        trade = Trade(
            entry_time=datetime(2024, 1, 1, 10, 0),
            exit_time=datetime(2024, 1, 1, 10, 30),
            entry_price=16200.0,
            exit_price=16240.0,
            direction="LONG",
            contracts=2,
            pnl=1600.0,  # 40 points * 2 contracts * $20/point
            pnl_percent=2.5,
            duration_minutes=30,
            setup_type="FVG_BULLISH",
            win=True
        )

        assert trade.direction == "LONG"
        assert trade.pnl == 1600.0
        assert trade.win is True
        assert trade.setup_type == "FVG_BULLISH"


class TestPositionScaler:
    """Test position sizing functionality"""

    def test_scaler_initialization(self):
        """Test scaler can be initialized"""
        scaler = PositionScaler(
            base_contracts=1,
            max_contracts=8
        )

        assert scaler.base_contracts == 1
        assert scaler.max_contracts == 8

    def test_consecutive_wins(self):
        """Test consecutive win counting"""
        scaler = PositionScaler()

        # Create trades with wins
        trades = [
            Trade(
                entry_time=datetime.now() - timedelta(hours=i),
                exit_time=datetime.now() - timedelta(hours=i-1),
                entry_price=100.0,
                exit_price=101.0,
                direction="LONG",
                contracts=1,
                pnl=100.0,
                pnl_percent=1.0,
                duration_minutes=30,
                setup_type="TEST",
                win=True
            )
            for i in range(5, 0, -1)
        ]

        consecutive = scaler.count_consecutive_wins(trades)
        assert consecutive == 5

    def test_consecutive_losses(self):
        """Test consecutive loss counting"""
        scaler = PositionScaler()

        # Create trades with losses
        trades = [
            Trade(
                entry_time=datetime.now() - timedelta(hours=i),
                exit_time=datetime.now() - timedelta(hours=i-1),
                entry_price=100.0,
                exit_price=99.0,
                direction="LONG",
                contracts=1,
                pnl=-100.0,
                pnl_percent=-1.0,
                duration_minutes=30,
                setup_type="TEST",
                win=False
            )
            for i in range(3, 0, -1)
        ]

        consecutive = scaler.count_consecutive_losses(trades)
        assert consecutive == 3

    def test_position_scaling(self):
        """Test position scaling logic"""
        scaler = PositionScaler(base_contracts=1, scale_up_threshold=3)

        # Create trades with different streaks
        # 3 consecutive wins → should scale to 2 contracts
        winning_trades = [
            Trade(
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                entry_price=100.0,
                exit_price=101.0,
                direction="LONG",
                contracts=1,
                pnl=100.0,
                pnl_percent=1.0,
                duration_minutes=30,
                setup_type="TEST",
                win=True
            )
            for _ in range(3)
        ]

        size = scaler.calculate_contracts_from_streak(winning_trades)
        assert size == 2  # Scaled up after 3 wins

        # 6 consecutive wins → should scale to 4 contracts
        more_wins = winning_trades + [
            Trade(
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                entry_price=100.0,
                exit_price=101.0,
                direction="LONG",
                contracts=1,
                pnl=100.0,
                pnl_percent=1.0,
                duration_minutes=30,
                setup_type="TEST",
                win=True
            )
            for _ in range(3)
        ]

        size = scaler.calculate_contracts_from_streak(more_wins)
        assert size == 4  # Scaled up after 6 wins

    def test_scale_down_on_losses(self):
        """Test scaling down after losses"""
        scaler = PositionScaler(base_contracts=1, scale_down_threshold=2)

        # Create trades with 2 consecutive losses
        losing_trades = [
            Trade(
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                entry_price=100.0,
                exit_price=99.0,
                direction="LONG",
                contracts=1,
                pnl=-100.0,
                pnl_percent=-1.0,
                duration_minutes=30,
                setup_type="TEST",
                win=False
            )
            for _ in range(2)
        ]

        size = scaler.calculate_contracts_from_streak(losing_trades)
        assert size == 1  # Scaled down to base

    def test_kelly_criterion(self):
        """Test Kelly Criterion calculation"""
        scaler = PositionScaler()

        # Create stats with positive expectancy
        from src.analysis.position_scaler import PerformanceStats

        stats = PerformanceStats(
            win_rate=60.0,  # 60% win rate
            average_winner=200.0,
            average_loser=-100.0,  # 2:1 reward:risk
            consecutive_wins=0,
            consecutive_losses=0,
            total_trades=20,
            recent_trades=[]
        )

        kelly = scaler.calculate_kelly_size(stats)

        # Kelly should be positive
        assert kelly > 0

        # Kelly should be reasonable (not crazy)
        assert kelly < 0.5

    def test_performance_stats_calculation(self):
        """Test performance stats calculation"""
        # Create sample trades
        trades = [
            Trade(
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                entry_price=100.0,
                exit_price=102.0,
                direction="LONG",
                contracts=1,
                pnl=200.0,
                pnl_percent=2.0,
                duration_minutes=30,
                setup_type="TEST",
                win=True
            )
            for _ in range(6)
        ] + [
            Trade(
                entry_time=datetime.now(),
                exit_time=datetime.now(),
                entry_price=100.0,
                exit_price=99.0,
                direction="LONG",
                contracts=1,
                pnl=-100.0,
                pnl_percent=-1.0,
                duration_minutes=30,
                setup_type="TEST",
                win=False
            )
            for _ in range(4)
        ]

        stats = calculate_performance_stats(trades)

        assert stats.total_trades == 10
        assert stats.win_rate == 60.0  # 6/10 = 60%
        assert stats.average_winner == 200.0
        assert stats.average_loser == -100.0


if __name__ == '__main__':
    pytest.main([__file__, '-v', '-s'])
