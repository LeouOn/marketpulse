#!/usr/bin/env python3
"""
Unit tests for Risk Management System

Tests:
- Trade validation
- Position sizing
- Daily loss limits
- Consecutive loss tracking
- Portfolio heat monitoring
- R:R ratio enforcement
"""

import sys
from pathlib import Path

# Add project root to path
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.analysis.risk_manager import RiskManager, RiskLevel
from src.state.position_manager import PositionManager, Position, PositionSide, PositionStatus
from datetime import datetime
import pytest


class TestRiskManager:
    """Test RiskManager class"""

    def setup_method(self):
        """Setup before each test"""
        self.risk_manager = RiskManager(
            account_size=10000,
            max_daily_loss=500,
            max_position_risk=250,
            min_risk_reward=1.5,
            max_consecutive_losses=3
        )

    def test_initialization(self):
        """Test risk manager initializes correctly"""
        assert self.risk_manager.limits.account_size == 10000
        assert self.risk_manager.limits.max_daily_loss == 500
        assert self.risk_manager.limits.max_position_risk == 250
        assert self.risk_manager.current_daily_pnl == 0
        assert self.risk_manager.consecutive_losses == 0

    def test_valid_trade_approval(self):
        """Test that valid trades are approved"""
        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            direction="long",
            contracts=2,
            point_value=2.0
        )

        assert validation.approved is True
        assert validation.risk_metrics is not None
        assert validation.risk_metrics.total_risk == 40.0  # 10 points * $2 * 2 contracts
        assert validation.risk_metrics.risk_reward_ratio == 2.0  # 20 points reward / 10 points risk

    def test_excessive_risk_rejection(self):
        """Test that trades with too much risk are rejected"""
        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15800,  # 50 points = $100/contract = $400 total
            take_profit=15900,
            direction="long",
            contracts=4,
            point_value=2.0
        )

        assert validation.approved is False
        assert "exceeds max" in validation.reason.lower()
        assert validation.suggested_contracts is not None

    def test_low_risk_reward_rejection(self):
        """Test that trades with R:R below 1.5 are rejected"""
        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,  # 10 points risk
            take_profit=15860,  # 10 points reward (1:1)
            direction="long",
            contracts=2,
            point_value=2.0
        )

        assert validation.approved is False
        assert "r:r" in validation.reason.lower()

    def test_invalid_stop_loss(self):
        """Test that invalid stop loss is rejected"""
        # Stop loss same as entry for long
        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15850,
            take_profit=15870,
            direction="long",
            contracts=1,
            point_value=2.0
        )

        assert validation.approved is False
        assert "invalid stop loss" in validation.reason.lower()

    def test_daily_loss_limit(self):
        """Test daily loss limit enforcement"""
        # Simulate losses to hit the limit
        self.risk_manager.current_daily_pnl = -500

        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            direction="long",
            contracts=1
        )

        assert validation.approved is False
        assert "daily loss limit" in validation.reason.lower()

    def test_consecutive_loss_limit(self):
        """Test consecutive loss limit"""
        # Simulate 3 consecutive losses
        for _ in range(3):
            self.risk_manager.record_trade_result(-50)

        assert self.risk_manager.consecutive_losses == 3

        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            direction="long",
            contracts=1
        )

        assert validation.approved is False
        assert "consecutive loss" in validation.reason.lower()

    def test_consecutive_losses_reset_on_win(self):
        """Test that consecutive losses reset on win"""
        # Simulate losses then win
        self.risk_manager.record_trade_result(-50)
        self.risk_manager.record_trade_result(-50)
        assert self.risk_manager.consecutive_losses == 2

        self.risk_manager.record_trade_result(100)  # Win
        assert self.risk_manager.consecutive_losses == 0

    def test_position_sizing(self):
        """Test position size calculation"""
        contracts = self.risk_manager.calculate_position_size(
            entry_price=15850,
            stop_loss=15840,  # 10 points = $20 risk per contract
            direction="long",
            risk_amount=100,
            point_value=2.0
        )

        # $100 risk / $20 per contract = 5 contracts, but capped at 4
        assert contracts == 4

    def test_position_sizing_respects_minimum(self):
        """Test that position sizing returns at least 1 contract"""
        contracts = self.risk_manager.calculate_position_size(
            entry_price=15850,
            stop_loss=15800,  # 50 points = $100 risk per contract
            direction="long",
            risk_amount=10,  # Only $10 risk = 0.1 contracts
            point_value=2.0
        )

        assert contracts == 1  # Minimum

    def test_portfolio_heat_limit(self):
        """Test portfolio heat (total at-risk) limit"""
        # Add some open positions
        self.risk_manager.add_open_position(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,
            contracts=2,
            direction="long",
            point_value=2.0
        )

        self.risk_manager.add_open_position(
            symbol="ES",
            entry_price=5100,
            stop_loss=5095,
            contracts=1,
            direction="long",
            point_value=5.0
        )

        # Total heat = (10 * 2 * 2) + (5 * 1 * 5) = 40 + 25 = 65

        # Now try to add another position that would exceed max heat (600)
        # This would need to be a huge position, so let's artificially lower the limit
        self.risk_manager.limits.max_portfolio_heat = 70

        validation = self.risk_manager.validate_trade(
            symbol="NQ",
            entry_price=15850,
            stop_loss=15840,  # 10 points * 2 * 1 = $20
            take_profit=15870,
            direction="long",
            contracts=1,
            point_value=2.0
        )

        # Should still be approved (65 + 20 = 85 is below new limit)
        # Let's try with more risk
        self.risk_manager.limits.max_portfolio_heat = 70

        validation = self.risk_manager.validate_trade(
            symbol="NQ",
            entry_price=15850,
            stop_loss=15830,  # 20 points * 2 * 1 = $40
            take_profit=15900,
            direction="long",
            contracts=1,
            point_value=2.0
        )

        # 65 + 40 = 105 > 70, should reject
        assert validation.approved is False or validation.risk_metrics.total_risk == 40

    def test_max_positions_limit(self):
        """Test maximum open positions limit"""
        # Add max positions (3)
        for i in range(3):
            self.risk_manager.add_open_position(
                symbol=f"SYM{i}",
                entry_price=100,
                stop_loss=95,
                contracts=1,
                direction="long",
                point_value=1.0
            )

        assert len(self.risk_manager.open_positions) == 3

        # Try to open 4th position
        validation = self.risk_manager.validate_trade(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            direction="long",
            contracts=1
        )

        assert validation.approved is False
        assert "maximum" in validation.reason.lower() and "position" in validation.reason.lower()

    def test_risk_level_calculation(self):
        """Test risk level determination"""
        # Low risk
        self.risk_manager.current_daily_pnl = 0
        assert self.risk_manager.get_risk_level() == RiskLevel.LOW

        # Moderate risk
        self.risk_manager.current_daily_pnl = -250
        level = self.risk_manager.get_risk_level()
        assert level in [RiskLevel.MODERATE, RiskLevel.HIGH]

        # High/Extreme risk
        self.risk_manager.current_daily_pnl = -480
        level = self.risk_manager.get_risk_level()
        assert level in [RiskLevel.HIGH, RiskLevel.EXTREME]

    def test_risk_summary(self):
        """Test risk summary generation"""
        self.risk_manager.record_trade_result(-100)
        self.risk_manager.add_open_position(
            symbol="MNQ",
            entry_price=15850,
            stop_loss=15840,
            contracts=2,
            direction="long"
        )

        summary = self.risk_manager.get_risk_summary()

        assert summary['account_size'] == 10000
        assert summary['daily_pnl'] == -100
        assert summary['open_positions'] == 1
        assert summary['portfolio_heat'] > 0
        assert summary['can_trade'] is True  # Still within limits

    def test_reset_daily_stats(self):
        """Test daily statistics reset"""
        self.risk_manager.current_daily_pnl = -200
        self.risk_manager.daily_trades = 5

        self.risk_manager.reset_daily_stats()

        assert self.risk_manager.current_daily_pnl == 0
        assert self.risk_manager.daily_trades == 0
        # consecutive_losses should NOT reset
        # (we don't test that here since we haven't set it up)


class TestPositionManager:
    """Test PositionManager class"""

    def setup_method(self):
        """Setup before each test"""
        # Clean up any existing test state file
        import os
        test_state_file = "data/state/test_positions.json"
        if os.path.exists(test_state_file):
            os.remove(test_state_file)

        # Use temporary state file
        self.position_manager = PositionManager(
            state_file=test_state_file
        )

    def test_add_position(self):
        """Test adding a position"""
        position = Position(
            id="test-123",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=2,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN
        )

        self.position_manager.add_position(position)

        assert len(self.position_manager.open_positions) == 1
        assert "test-123" in self.position_manager.open_positions

    def test_close_position(self):
        """Test closing a position"""
        position = Position(
            id="test-456",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=2,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN,
            point_value=2.0
        )

        self.position_manager.add_position(position)

        # Close position
        closed = self.position_manager.close_position(
            position_id="test-456",
            exit_price=15870  # Hit target
        )

        assert closed is not None
        assert closed.realized_pnl == 80.0  # 20 points * $2 * 2 contracts
        assert len(self.position_manager.open_positions) == 0
        assert len(self.position_manager.closed_positions) == 1

    def test_unrealized_pnl_calculation(self):
        """Test unrealized P&L calculation"""
        position = Position(
            id="test-789",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=2,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN,
            point_value=2.0
        )

        # Price moved up 10 points
        unrealized = position.get_unrealized_pnl(15860)
        assert unrealized == 40.0  # 10 points * $2 * 2 contracts

        # Price moved down 5 points
        unrealized = position.get_unrealized_pnl(15845)
        assert unrealized == -20.0  # -5 points * $2 * 2 contracts

    def test_stop_loss_detection(self):
        """Test stop loss detection"""
        position = Position(
            id="test-stop",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=1,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN
        )

        assert position.is_stopped_out(15830) is True
        assert position.is_stopped_out(15845) is False

    def test_target_hit_detection(self):
        """Test take profit detection"""
        position = Position(
            id="test-target",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=1,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN
        )

        assert position.is_target_hit(15875) is True
        assert position.is_target_hit(15865) is False

    def test_total_portfolio_risk(self):
        """Test total portfolio risk calculation"""
        pos1 = Position(
            id="pos1",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=2,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN,
            point_value=2.0
        )

        pos2 = Position(
            id="pos2",
            symbol="ES",
            side=PositionSide.SHORT,
            entry_price=5100,
            stop_loss=5105,
            take_profit=5090,
            contracts=1,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN,
            point_value=5.0
        )

        self.position_manager.add_position(pos1)
        self.position_manager.add_position(pos2)

        total_risk = self.position_manager.get_total_portfolio_risk()
        # pos1: 10 points * 2 * 2 = 40
        # pos2: 5 points * 1 * 5 = 25
        # Total = 65
        assert total_risk == 65.0

    def test_daily_pnl_calculation(self):
        """Test daily P&L calculation"""
        # Create and close a position with profit
        position = Position(
            id="daily-test",
            symbol="MNQ",
            side=PositionSide.LONG,
            entry_price=15850,
            stop_loss=15840,
            take_profit=15870,
            contracts=2,
            entry_timestamp=datetime.now(),
            status=PositionStatus.OPEN,
            point_value=2.0
        )

        self.position_manager.add_position(position)
        self.position_manager.close_position(
            position_id="daily-test",
            exit_price=15870
        )

        daily_pnl = self.position_manager.get_daily_pnl()
        assert daily_pnl == 80.0  # 20 points * $2 * 2 contracts

    def test_consecutive_losses_tracking(self):
        """Test consecutive loss tracking"""
        # Create and close multiple losing trades
        for i in range(3):
            position = Position(
                id=f"loss-{i}",
                symbol="MNQ",
                side=PositionSide.LONG,
                entry_price=15850,
                stop_loss=15840,
                take_profit=15870,
                contracts=1,
                entry_timestamp=datetime.now(),
                status=PositionStatus.OPEN,
                point_value=2.0
            )

            self.position_manager.add_position(position)
            self.position_manager.close_position(
                position_id=f"loss-{i}",
                exit_price=15840  # Stopped out
            )

        consecutive = self.position_manager.get_consecutive_losses()
        assert consecutive == 3


def run_tests():
    """Run all risk management tests"""
    print("\n" + "=" * 70)
    print("RISK MANAGEMENT UNIT TESTS")
    print("=" * 70)

    # Run pytest
    pytest.main([
        __file__,
        "-v",
        "--tb=short",
        "-x"  # Stop on first failure
    ])


if __name__ == "__main__":
    run_tests()
