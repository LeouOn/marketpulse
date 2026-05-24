"""
Risk Management Engine

Systematic risk controls to protect capital and prevent catastrophic losses.

Key Features:
- Daily loss limits
- Per-trade position sizing
- Risk/Reward validation
- Portfolio heat tracking
- Maximum drawdown monitoring
"""

from dataclasses import dataclass
from typing import Tuple, Optional, Dict, Any, List
from datetime import datetime, timedelta
from enum import Enum
from loguru import logger
import pandas as pd


class RiskLevel(Enum):
    """Risk level categories"""
    LOW = "low"
    MODERATE = "moderate"
    HIGH = "high"
    EXTREME = "extreme"


@dataclass
class RiskLimits:
    """Risk limit configuration"""
    account_size: float
    max_daily_loss: float  # Absolute dollar amount
    max_daily_loss_pct: float  # Percentage of account
    max_position_risk: float  # Per-trade risk
    max_position_risk_pct: float  # Percentage per trade
    max_portfolio_heat: float  # Total at-risk across all positions
    max_consecutive_losses: int  # Stop trading after N losses
    min_risk_reward: float  # Minimum R:R ratio
    max_positions: int  # Maximum concurrent positions
    max_contracts_per_trade: int  # Contract limit


@dataclass
class TradeRisk:
    """Risk metrics for a single trade"""
    entry_price: float
    stop_loss: float
    take_profit: float
    contracts: int
    risk_per_contract: float
    total_risk: float
    total_reward: float
    risk_reward_ratio: float
    risk_percentage: float  # Of account


@dataclass
class RiskValidation:
    """Result of risk validation"""
    approved: bool
    reason: str
    warnings: List[str]
    risk_metrics: Optional[TradeRisk] = None
    suggested_contracts: Optional[int] = None


class RiskManager:
    """
    Comprehensive risk management system

    Protects capital with systematic rules:
    - Daily loss limits
    - Position sizing
    - Risk/Reward requirements
    - Portfolio heat tracking
    """

    def __init__(
        self,
        account_size: float = 10000,
        max_daily_loss: float = 500,
        max_position_risk: float = 250,
        min_risk_reward: float = 1.5,
        max_consecutive_losses: int = 3
    ):
        """
        Initialize risk manager

        Args:
            account_size: Total account size
            max_daily_loss: Maximum loss per day ($)
            max_position_risk: Maximum risk per trade ($)
            min_risk_reward: Minimum R:R ratio
            max_consecutive_losses: Stop after N consecutive losses
        """
        self.limits = RiskLimits(
            account_size=account_size,
            max_daily_loss=max_daily_loss,
            max_daily_loss_pct=max_daily_loss / account_size,
            max_position_risk=max_position_risk,
            max_position_risk_pct=max_position_risk / account_size,
            max_portfolio_heat=account_size * 0.06,  # 6% max total heat
            max_consecutive_losses=max_consecutive_losses,
            min_risk_reward=min_risk_reward,
            max_positions=3,
            max_contracts_per_trade=4  # MNQ limit
        )

        # Current state (in production, load from database)
        self.current_daily_pnl = 0.0
        self.consecutive_losses = 0
        self.open_positions: List[Dict[str, Any]] = []
        self.daily_trades = 0

        logger.info(
            f"Risk Manager initialized: Account=${account_size:,.0f}, "
            f"Max Daily Loss=${max_daily_loss}, "
            f"Max Position Risk=${max_position_risk}"
        )

    def validate_trade(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        take_profit: float,
        direction: str,
        contracts: int = 1,
        point_value: float = 2.0  # $2 per point for MNQ
    ) -> RiskValidation:
        """
        Comprehensive trade validation

        Args:
            symbol: Trading symbol (e.g., "MNQ")
            entry_price: Entry price
            stop_loss: Stop loss price
            take_profit: Target price
            direction: "long" or "short"
            contracts: Number of contracts
            point_value: Dollar value per point

        Returns:
            RiskValidation with approval status and details
        """
        warnings = []

        # Calculate risk metrics
        if direction.lower() == "long":
            risk_points = entry_price - stop_loss
            reward_points = take_profit - entry_price
        else:  # short
            risk_points = stop_loss - entry_price
            reward_points = entry_price - take_profit

        if risk_points <= 0:
            return RiskValidation(
                approved=False,
                reason="Invalid stop loss: Stop must be beyond entry price",
                warnings=[]
            )

        if reward_points <= 0:
            return RiskValidation(
                approved=False,
                reason="Invalid take profit: Target must be beyond entry price",
                warnings=[]
            )

        risk_per_contract = risk_points * point_value
        total_risk = risk_per_contract * contracts
        total_reward = reward_points * point_value * contracts
        risk_reward_ratio = reward_points / risk_points
        risk_percentage = (total_risk / self.limits.account_size) * 100

        risk_metrics = TradeRisk(
            entry_price=entry_price,
            stop_loss=stop_loss,
            take_profit=take_profit,
            contracts=contracts,
            risk_per_contract=risk_per_contract,
            total_risk=total_risk,
            total_reward=total_reward,
            risk_reward_ratio=risk_reward_ratio,
            risk_percentage=risk_percentage
        )

        # Validation checks

        # 1. Daily loss limit
        if self.current_daily_pnl <= -self.limits.max_daily_loss:
            return RiskValidation(
                approved=False,
                reason=f"Daily loss limit reached: ${self.current_daily_pnl:.2f} / -${self.limits.max_daily_loss}",
                warnings=warnings,
                risk_metrics=risk_metrics
            )

        # 2. Would this trade exceed daily limit?
        potential_daily_loss = self.current_daily_pnl - total_risk
        if potential_daily_loss < -self.limits.max_daily_loss:
            # Suggest reduced position
            max_affordable_risk = self.limits.max_daily_loss + self.current_daily_pnl
            suggested_contracts = max(1, int(max_affordable_risk / risk_per_contract))

            return RiskValidation(
                approved=False,
                reason=f"Trade risk ${total_risk:.0f} would exceed daily limit. Current P&L: ${self.current_daily_pnl:.2f}",
                warnings=[f"Consider reducing to {suggested_contracts} contract(s)"],
                risk_metrics=risk_metrics,
                suggested_contracts=suggested_contracts
            )

        # 3. Per-trade position risk
        if total_risk > self.limits.max_position_risk:
            suggested_contracts = max(1, int(self.limits.max_position_risk / risk_per_contract))

            return RiskValidation(
                approved=False,
                reason=f"Position risk ${total_risk:.0f} exceeds max ${self.limits.max_position_risk:.0f}",
                warnings=[f"Reduce to {suggested_contracts} contract(s) or tighten stop"],
                risk_metrics=risk_metrics,
                suggested_contracts=suggested_contracts
            )

        # 4. Risk/Reward ratio
        if risk_reward_ratio < self.limits.min_risk_reward:
            return RiskValidation(
                approved=False,
                reason=f"R:R {risk_reward_ratio:.2f} below minimum {self.limits.min_risk_reward}",
                warnings=["Widen target or tighten stop"],
                risk_metrics=risk_metrics
            )

        # 5. Consecutive losses
        if self.consecutive_losses >= self.limits.max_consecutive_losses:
            return RiskValidation(
                approved=False,
                reason=f"Stop trading: {self.consecutive_losses} consecutive losses. Take a break.",
                warnings=["Review recent trades", "Check if market conditions changed"],
                risk_metrics=risk_metrics
            )

        # 6. Portfolio heat (total at-risk)
        current_heat = sum(pos.get('risk', 0) for pos in self.open_positions)
        new_heat = current_heat + total_risk

        if new_heat > self.limits.max_portfolio_heat:
            return RiskValidation(
                approved=False,
                reason=f"Portfolio heat ${new_heat:.0f} exceeds max ${self.limits.max_portfolio_heat:.0f}",
                warnings=[f"Close positions or wait. Current heat: ${current_heat:.0f}"],
                risk_metrics=risk_metrics
            )

        # 7. Max positions
        if len(self.open_positions) >= self.limits.max_positions:
            return RiskValidation(
                approved=False,
                reason=f"Maximum {self.limits.max_positions} positions already open",
                warnings=["Close a position before opening new one"],
                risk_metrics=risk_metrics
            )

        # Warnings (non-blocking)

        if risk_percentage > 3.0:
            warnings.append(f"High risk: {risk_percentage:.1f}% of account")

        if risk_reward_ratio < 2.0:
            warnings.append(f"Low R:R: {risk_reward_ratio:.2f} (aim for 2:1+)")

        if self.consecutive_losses > 0:
            warnings.append(f"{self.consecutive_losses} consecutive loss(es) - trade carefully")

        # All checks passed
        return RiskValidation(
            approved=True,
            reason="Trade approved",
            warnings=warnings,
            risk_metrics=risk_metrics
        )

    def calculate_position_size(
        self,
        entry_price: float,
        stop_loss: float,
        direction: str,
        risk_amount: Optional[float] = None,
        point_value: float = 2.0
    ) -> int:
        """
        Calculate optimal position size based on risk

        Args:
            entry_price: Entry price
            stop_loss: Stop loss price
            direction: "long" or "short"
            risk_amount: Dollar amount to risk (defaults to max_position_risk)
            point_value: Dollar value per point

        Returns:
            Number of contracts
        """
        if risk_amount is None:
            risk_amount = self.limits.max_position_risk

        # Calculate points at risk
        if direction.lower() == "long":
            points_at_risk = entry_price - stop_loss
        else:
            points_at_risk = stop_loss - entry_price

        if points_at_risk <= 0:
            logger.warning("Invalid stop loss for position sizing")
            return 1

        # Calculate contracts
        risk_per_contract = points_at_risk * point_value
        contracts = int(risk_amount / risk_per_contract)

        # Apply limits
        contracts = max(1, contracts)  # Minimum 1
        contracts = min(contracts, self.limits.max_contracts_per_trade)  # Cap at max

        logger.info(
            f"Position size: {contracts} contracts "
            f"(Risk: ${risk_per_contract * contracts:.2f} "
            f"for {points_at_risk:.2f} points)"
        )

        return contracts

    def record_trade_result(self, pnl: float) -> None:
        """
        Record trade result and update state

        Args:
            pnl: Profit/Loss from trade
        """
        self.current_daily_pnl += pnl
        self.daily_trades += 1

        if pnl < 0:
            self.consecutive_losses += 1
            logger.warning(
                f"Loss recorded: ${pnl:.2f}. "
                f"Consecutive losses: {self.consecutive_losses}"
            )
        else:
            self.consecutive_losses = 0
            logger.info(f"Win recorded: ${pnl:.2f}")

        logger.info(
            f"Daily P&L: ${self.current_daily_pnl:.2f} "
            f"({self.daily_trades} trades)"
        )

        # Check if daily limit hit
        if self.current_daily_pnl <= -self.limits.max_daily_loss:
            logger.error(
                f"🛑 DAILY LOSS LIMIT HIT: ${self.current_daily_pnl:.2f}. "
                f"STOP TRADING FOR TODAY."
            )

    def add_open_position(
        self,
        symbol: str,
        entry_price: float,
        stop_loss: float,
        contracts: int,
        direction: str,
        point_value: float = 2.0
    ) -> None:
        """Track open position"""
        if direction.lower() == "long":
            risk_points = entry_price - stop_loss
        else:
            risk_points = stop_loss - entry_price

        risk = risk_points * point_value * contracts

        position = {
            'symbol': symbol,
            'entry': entry_price,
            'stop': stop_loss,
            'contracts': contracts,
            'direction': direction,
            'risk': risk,
            'timestamp': datetime.now()
        }

        self.open_positions.append(position)
        logger.info(f"Position opened: {symbol} {direction} x{contracts} @ {entry_price}")

    def remove_position(self, symbol: str) -> None:
        """Remove closed position"""
        self.open_positions = [p for p in self.open_positions if p['symbol'] != symbol]
        logger.info(f"Position closed: {symbol}")

    def get_portfolio_heat(self) -> float:
        """Get total at-risk amount across all positions"""
        return sum(pos.get('risk', 0) for pos in self.open_positions)

    def get_risk_level(self) -> RiskLevel:
        """Determine current risk level"""
        # Based on daily P&L and portfolio heat
        daily_loss_pct = abs(self.current_daily_pnl) / self.limits.account_size
        heat_pct = self.get_portfolio_heat() / self.limits.account_size

        max_pct = max(daily_loss_pct, heat_pct)

        if max_pct < 0.02:
            return RiskLevel.LOW
        elif max_pct < 0.04:
            return RiskLevel.MODERATE
        elif max_pct < 0.06:
            return RiskLevel.HIGH
        else:
            return RiskLevel.EXTREME

    def get_risk_summary(self) -> Dict[str, Any]:
        """Get current risk summary"""
        portfolio_heat = self.get_portfolio_heat()
        risk_level = self.get_risk_level()

        return {
            'account_size': self.limits.account_size,
            'daily_pnl': self.current_daily_pnl,
            'daily_limit': self.limits.max_daily_loss,
            'daily_limit_used_pct': (abs(self.current_daily_pnl) / self.limits.max_daily_loss) * 100,
            'portfolio_heat': portfolio_heat,
            'max_heat': self.limits.max_portfolio_heat,
            'heat_used_pct': (portfolio_heat / self.limits.max_portfolio_heat) * 100,
            'open_positions': len(self.open_positions),
            'max_positions': self.limits.max_positions,
            'consecutive_losses': self.consecutive_losses,
            'daily_trades': self.daily_trades,
            'risk_level': risk_level.value,
            'can_trade': (
                self.current_daily_pnl > -self.limits.max_daily_loss and
                self.consecutive_losses < self.limits.max_consecutive_losses
            )
        }

    def reset_daily_stats(self) -> None:
        """Reset daily statistics (call at start of new trading day)"""
        logger.info(
            f"Resetting daily stats. Previous P&L: ${self.current_daily_pnl:.2f}, "
            f"Trades: {self.daily_trades}"
        )

        self.current_daily_pnl = 0.0
        self.daily_trades = 0
        # Note: consecutive_losses persists across days intentionally
