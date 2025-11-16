"""
Auto-Scaling Position Size System

Scale position size based on:
- Recent performance (consecutive wins/losses)
- Kelly Criterion
- Risk management rules
- Market conditions
"""

import numpy as np
from typing import List, Dict, Any, Optional
from dataclasses import dataclass
from loguru import logger


@dataclass
class PerformanceStats:
    """Recent performance statistics"""
    win_rate: float
    average_winner: float
    average_loser: float
    consecutive_wins: int
    consecutive_losses: int
    total_trades: int
    recent_trades: List[Any]  # List of recent Trade objects


class PositionScaler:
    """
    Automatically scale position size based on performance

    Strategy:
    - Start with 1 contract (base)
    - Scale up after consecutive wins (3 wins → 2 contracts, 6 wins → 4 contracts)
    - Scale down immediately after 2 consecutive losses → back to 1 contract
    - Combine with Kelly Criterion for optimal sizing
    - Never exceed maximum position size
    """

    def __init__(
        self,
        base_contracts: int = 1,
        max_contracts: int = 8,
        scale_up_threshold: int = 3,
        scale_down_threshold: int = 2,
        kelly_fraction: float = 0.25  # Use 25% of Kelly recommendation (safer)
    ):
        """
        Initialize position scaler

        Args:
            base_contracts: Starting position size
            max_contracts: Maximum allowed contracts
            scale_up_threshold: Consecutive wins needed to scale up
            scale_down_threshold: Consecutive losses to scale down
            kelly_fraction: Fraction of Kelly Criterion to use (0.25 = quarter Kelly)
        """
        self.base_contracts = base_contracts
        self.max_contracts = max_contracts
        self.scale_up_threshold = scale_up_threshold
        self.scale_down_threshold = scale_down_threshold
        self.kelly_fraction = kelly_fraction

        logger.info(f"PositionScaler initialized: base={base_contracts}, max={max_contracts}")

    def count_consecutive_wins(self, recent_trades: List[Any]) -> int:
        """Count consecutive wins from end of trade list"""
        if not recent_trades:
            return 0

        consecutive = 0
        for trade in reversed(recent_trades):
            if hasattr(trade, 'win') and trade.win:
                consecutive += 1
            else:
                break

        return consecutive

    def count_consecutive_losses(self, recent_trades: List[Any]) -> int:
        """Count consecutive losses from end of trade list"""
        if not recent_trades:
            return 0

        consecutive = 0
        for trade in reversed(recent_trades):
            if hasattr(trade, 'win') and not trade.win:
                consecutive += 1
            else:
                break

        return consecutive

    def calculate_contracts_from_streak(self, recent_trades: List[Any]) -> int:
        """
        Calculate contracts based on consecutive performance

        Strategy:
        - 1 contract: default or after losses
        - 2 contracts: after 3 consecutive wins
        - 4 contracts: after 6 consecutive wins
        - Back to 1 contract: after 2 consecutive losses

        Args:
            recent_trades: List of recent trades

        Returns:
            Number of contracts
        """
        consecutive_wins = self.count_consecutive_wins(recent_trades)
        consecutive_losses = self.count_consecutive_losses(recent_trades)

        # Scale down immediately on losses
        if consecutive_losses >= self.scale_down_threshold:
            logger.info(f"Scaling down to {self.base_contracts} contracts after {consecutive_losses} losses")
            return self.base_contracts

        # Scale up gradually on wins
        if consecutive_wins >= 6:
            contracts = 4
            logger.info(f"Scaling up to {contracts} contracts after {consecutive_wins} consecutive wins")
            return contracts
        elif consecutive_wins >= self.scale_up_threshold:
            contracts = 2
            logger.info(f"Scaling up to {contracts} contracts after {consecutive_wins} consecutive wins")
            return contracts
        else:
            return self.base_contracts

    def calculate_kelly_size(self, stats: PerformanceStats) -> float:
        """
        Calculate optimal position size using Kelly Criterion

        Formula: f = (bp - q) / b
        Where:
        - f = fraction of capital to risk
        - b = odds (avg_win / avg_loss)
        - p = win rate
        - q = loss rate (1 - p)

        Args:
            stats: Performance statistics

        Returns:
            Kelly fraction (0-1)
        """
        if stats.win_rate == 0 or stats.average_loser == 0 or stats.total_trades < 10:
            return 0.0

        # Calculate odds
        b = abs(stats.average_winner / stats.average_loser)

        # Win/loss probabilities
        p = stats.win_rate / 100.0  # Convert percentage to decimal
        q = 1 - p

        # Kelly formula
        kelly = (b * p - q) / b

        # Clamp to reasonable bounds
        kelly = max(0, min(kelly, 1.0))

        # Use fractional Kelly (usually 25% or 50% of full Kelly for safety)
        fractional_kelly = kelly * self.kelly_fraction

        return fractional_kelly

    def get_recommended_size(
        self,
        stats: PerformanceStats,
        account_balance: float = 10000,
        use_kelly: bool = True
    ) -> int:
        """
        Get recommended position size combining streak and Kelly

        Args:
            stats: Performance statistics
            account_balance: Current account balance
            use_kelly: Whether to use Kelly Criterion

        Returns:
            Recommended number of contracts
        """
        # Get base size from consecutive performance
        streak_contracts = self.calculate_contracts_from_streak(stats.recent_trades)

        if not use_kelly or stats.total_trades < 10:
            # Not enough data for Kelly, just use streak
            return min(streak_contracts, self.max_contracts)

        # Calculate Kelly fraction
        kelly_fraction = self.calculate_kelly_size(stats)

        if kelly_fraction <= 0:
            # Kelly says don't trade (negative edge)
            logger.warning("Kelly Criterion suggests negative edge - reducing to minimum size")
            return self.base_contracts

        # Convert Kelly fraction to contracts
        # Assume each contract needs ~$1000 margin for futures
        margin_per_contract = 1000
        max_contracts_from_kelly = int((account_balance * kelly_fraction) / margin_per_contract)

        # Combine streak multiplier with Kelly
        # Use Kelly as upper bound, streak as multiplier
        recommended = min(streak_contracts, max_contracts_from_kelly)

        # Ensure within bounds
        recommended = max(self.base_contracts, min(recommended, self.max_contracts))

        logger.info(f"Recommended size: {recommended} contracts "
                   f"(streak: {streak_contracts}, kelly: {max_contracts_from_kelly}, "
                   f"kelly_fraction: {kelly_fraction:.3f})")

        return recommended

    def get_size_with_confidence(
        self,
        stats: PerformanceStats,
        signal_strength: float = 50.0,
        account_balance: float = 10000
    ) -> Dict[str, Any]:
        """
        Get position size with confidence metrics

        Args:
            stats: Performance statistics
            signal_strength: Signal strength (0-100)
            account_balance: Current account balance

        Returns:
            Dict with size and confidence metrics
        """
        # Base recommendation
        base_size = self.get_recommended_size(stats, account_balance)

        # Adjust for signal strength
        # High strength signals (>80) can use full size
        # Low strength signals (<50) should use reduced size
        if signal_strength >= 80:
            strength_multiplier = 1.0
        elif signal_strength >= 70:
            strength_multiplier = 0.75
        elif signal_strength >= 60:
            strength_multiplier = 0.5
        else:
            strength_multiplier = 0.25

        adjusted_size = int(base_size * strength_multiplier)
        adjusted_size = max(self.base_contracts, min(adjusted_size, self.max_contracts))

        # Calculate confidence metrics
        confidence = self._calculate_confidence(stats, signal_strength)

        return {
            'contracts': adjusted_size,
            'base_size': base_size,
            'strength_multiplier': strength_multiplier,
            'signal_strength': signal_strength,
            'confidence': confidence,
            'consecutive_wins': stats.consecutive_wins,
            'consecutive_losses': stats.consecutive_losses,
            'win_rate': stats.win_rate,
            'kelly_fraction': self.calculate_kelly_size(stats),
            'reason': self._get_sizing_reason(stats, signal_strength, adjusted_size)
        }

    def _calculate_confidence(self, stats: PerformanceStats, signal_strength: float) -> float:
        """
        Calculate overall confidence score (0-100)

        Factors:
        - Win rate
        - Sample size
        - Recent performance (streak)
        - Signal strength
        """
        # Win rate factor (0-30 points)
        win_rate_score = min(30, stats.win_rate * 0.5)

        # Sample size factor (0-20 points)
        sample_size_score = min(20, stats.total_trades * 0.5)

        # Streak factor (0-25 points)
        if stats.consecutive_wins >= 5:
            streak_score = 25
        elif stats.consecutive_wins >= 3:
            streak_score = 15
        elif stats.consecutive_losses >= 2:
            streak_score = 0
        else:
            streak_score = 10

        # Signal strength factor (0-25 points)
        signal_score = signal_strength * 0.25

        total_confidence = win_rate_score + sample_size_score + streak_score + signal_score

        return min(100, total_confidence)

    def _get_sizing_reason(self, stats: PerformanceStats, signal_strength: float, size: int) -> str:
        """Get human-readable reason for position size"""
        reasons = []

        if stats.consecutive_losses >= self.scale_down_threshold:
            reasons.append(f"Scaled down due to {stats.consecutive_losses} consecutive losses")
        elif stats.consecutive_wins >= 6:
            reasons.append(f"Scaled up due to {stats.consecutive_wins} consecutive wins")
        elif stats.consecutive_wins >= self.scale_up_threshold:
            reasons.append(f"Moderate scale-up after {stats.consecutive_wins} wins")

        if signal_strength >= 80:
            reasons.append("Strong signal strength")
        elif signal_strength < 60:
            reasons.append("Weak signal - reduced size")

        if stats.total_trades < 10:
            reasons.append("Limited trade history - conservative sizing")

        kelly = self.calculate_kelly_size(stats)
        if kelly > 0.3:
            reasons.append("Strong Kelly edge")
        elif kelly < 0.1:
            reasons.append("Weak Kelly edge - reduced size")

        if size == self.max_contracts:
            reasons.append("At maximum position size")
        elif size == self.base_contracts:
            reasons.append("At base position size")

        return "; ".join(reasons) if reasons else "Standard sizing"


def calculate_performance_stats(trades: List[Any]) -> PerformanceStats:
    """
    Calculate performance statistics from trade history

    Args:
        trades: List of Trade objects

    Returns:
        PerformanceStats object
    """
    if not trades:
        return PerformanceStats(
            win_rate=0.0,
            average_winner=0.0,
            average_loser=0.0,
            consecutive_wins=0,
            consecutive_losses=0,
            total_trades=0,
            recent_trades=[]
        )

    # Calculate win rate
    wins = [t for t in trades if t.win]
    losses = [t for t in trades if not t.win]
    win_rate = (len(wins) / len(trades)) * 100

    # Calculate averages
    average_winner = np.mean([t.pnl for t in wins]) if wins else 0.0
    average_loser = np.mean([t.pnl for t in losses]) if losses else 0.0

    # Count consecutive
    scaler = PositionScaler()
    consecutive_wins = scaler.count_consecutive_wins(trades)
    consecutive_losses = scaler.count_consecutive_losses(trades)

    return PerformanceStats(
        win_rate=win_rate,
        average_winner=average_winner,
        average_loser=average_loser,
        consecutive_wins=consecutive_wins,
        consecutive_losses=consecutive_losses,
        total_trades=len(trades),
        recent_trades=trades[-20:]  # Last 20 trades
    )
