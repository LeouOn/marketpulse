"""
Position and State Management

Centralized state management for:
- Open positions
- Daily P&L tracking
- Trade history
- Account state

Persistence across application restarts.
"""

from dataclasses import dataclass, asdict
from typing import List, Optional, Dict, Any
from datetime import datetime, date, timedelta
from enum import Enum
import json
from pathlib import Path
from loguru import logger


class PositionStatus(Enum):
    """Position status"""
    OPEN = "open"
    CLOSED = "closed"
    STOPPED_OUT = "stopped_out"
    TARGET_HIT = "target_hit"


class PositionSide(Enum):
    """Position direction"""
    LONG = "long"
    SHORT = "short"


@dataclass
class Position:
    """Trading position"""
    id: str  # Unique identifier
    symbol: str
    side: PositionSide
    entry_price: float
    stop_loss: float
    take_profit: float
    contracts: int
    entry_timestamp: datetime
    status: PositionStatus

    # Optional fields
    exit_price: Optional[float] = None
    exit_timestamp: Optional[datetime] = None
    realized_pnl: Optional[float] = None

    # Trade context
    setup_type: Optional[str] = None  # "FVG_FILL", "ORDER_BLOCK", etc.
    signal_confidence: Optional[float] = None
    cvd_at_entry: Optional[float] = None
    vix_at_entry: Optional[float] = None
    session: Optional[str] = None  # "London", "NY_Open", etc.
    tags: List[str] = None

    # Risk metrics
    risk_amount: Optional[float] = None
    point_value: float = 2.0  # MNQ default

    def __post_init__(self):
        if self.tags is None:
            self.tags = []

        # Calculate risk if not provided
        if self.risk_amount is None:
            if self.side == PositionSide.LONG:
                risk_points = self.entry_price - self.stop_loss
            else:
                risk_points = self.stop_loss - self.entry_price

            self.risk_amount = abs(risk_points) * self.point_value * self.contracts

    def get_unrealized_pnl(self, current_price: float) -> float:
        """Calculate unrealized P&L"""
        if self.side == PositionSide.LONG:
            points = current_price - self.entry_price
        else:
            points = self.entry_price - current_price

        return points * self.point_value * self.contracts

    def is_stopped_out(self, current_price: float) -> bool:
        """Check if stop loss hit"""
        if self.side == PositionSide.LONG:
            return current_price <= self.stop_loss
        else:
            return current_price >= self.stop_loss

    def is_target_hit(self, current_price: float) -> bool:
        """Check if take profit hit"""
        if self.side == PositionSide.LONG:
            return current_price >= self.take_profit
        else:
            return current_price <= self.take_profit

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['side'] = self.side.value
        data['status'] = self.status.value
        data['entry_timestamp'] = self.entry_timestamp.isoformat() if self.entry_timestamp else None
        data['exit_timestamp'] = self.exit_timestamp.isoformat() if self.exit_timestamp else None
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'Position':
        """Create from dictionary"""
        data['side'] = PositionSide(data['side'])
        data['status'] = PositionStatus(data['status'])
        data['entry_timestamp'] = datetime.fromisoformat(data['entry_timestamp']) if data['entry_timestamp'] else None
        data['exit_timestamp'] = datetime.fromisoformat(data['exit_timestamp']) if data['exit_timestamp'] else None
        return cls(**data)


@dataclass
class DailyStats:
    """Daily trading statistics"""
    date: date
    starting_balance: float
    ending_balance: float
    realized_pnl: float
    total_trades: int
    winning_trades: int
    losing_trades: int
    largest_win: float
    largest_loss: float
    gross_profit: float
    gross_loss: float

    def to_dict(self) -> Dict[str, Any]:
        """Convert to dictionary"""
        data = asdict(self)
        data['date'] = self.date.isoformat()
        return data

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailyStats':
        """Create from dictionary"""
        data['date'] = date.fromisoformat(data['date'])
        return cls(**data)


class PositionManager:
    """
    Centralized position and state management

    Handles:
    - Open positions tracking
    - Trade history
    - Daily statistics
    - Persistent state
    """

    def __init__(self, state_file: str = "data/state/positions.json"):
        """
        Initialize position manager

        Args:
            state_file: Path to state persistence file
        """
        self.state_file = Path(state_file)
        self.state_file.parent.mkdir(parents=True, exist_ok=True)

        # State
        self.open_positions: Dict[str, Position] = {}
        self.closed_positions: List[Position] = []
        self.daily_stats: Dict[date, DailyStats] = {}
        self.current_balance: float = 10000.0

        # Load persisted state
        self.load_state()

        logger.info(
            f"Position Manager initialized. "
            f"Open positions: {len(self.open_positions)}, "
            f"Balance: ${self.current_balance:,.2f}"
        )

    def add_position(self, position: Position) -> None:
        """
        Add new position

        Args:
            position: Position to add
        """
        self.open_positions[position.id] = position
        logger.info(
            f"Position added: {position.symbol} {position.side.value} "
            f"x{position.contracts} @ {position.entry_price}"
        )
        self.save_state()

    def close_position(
        self,
        position_id: str,
        exit_price: float,
        exit_timestamp: Optional[datetime] = None,
        status: PositionStatus = PositionStatus.CLOSED
    ) -> Optional[Position]:
        """
        Close position

        Args:
            position_id: Position ID
            exit_price: Exit price
            exit_timestamp: Exit timestamp (defaults to now)
            status: Exit status

        Returns:
            Closed position or None if not found
        """
        if position_id not in self.open_positions:
            logger.warning(f"Position {position_id} not found")
            return None

        position = self.open_positions.pop(position_id)
        position.exit_price = exit_price
        position.exit_timestamp = exit_timestamp or datetime.now()
        position.status = status

        # Calculate realized P&L
        if position.side == PositionSide.LONG:
            points = exit_price - position.entry_price
        else:
            points = position.entry_price - exit_price

        position.realized_pnl = points * position.point_value * position.contracts

        self.closed_positions.append(position)
        self.current_balance += position.realized_pnl

        logger.info(
            f"Position closed: {position.symbol} "
            f"P&L: ${position.realized_pnl:+.2f}, "
            f"New balance: ${self.current_balance:,.2f}"
        )

        # Update daily stats
        self._update_daily_stats(position)

        self.save_state()
        return position

    def get_position(self, position_id: str) -> Optional[Position]:
        """Get position by ID"""
        return self.open_positions.get(position_id)

    def get_all_open_positions(self) -> List[Position]:
        """Get all open positions"""
        return list(self.open_positions.values())

    def get_positions_by_symbol(self, symbol: str) -> List[Position]:
        """Get all open positions for symbol"""
        return [p for p in self.open_positions.values() if p.symbol == symbol]

    def get_total_portfolio_risk(self) -> float:
        """Get total at-risk amount"""
        return sum(p.risk_amount for p in self.open_positions.values())

    def get_unrealized_pnl(self, current_prices: Dict[str, float]) -> float:
        """
        Calculate total unrealized P&L

        Args:
            current_prices: Dict of symbol -> current price

        Returns:
            Total unrealized P&L
        """
        total = 0.0
        for position in self.open_positions.values():
            if position.symbol in current_prices:
                total += position.get_unrealized_pnl(current_prices[position.symbol])

        return total

    def get_daily_pnl(self, target_date: Optional[date] = None) -> float:
        """Get realized P&L for specific day"""
        target_date = target_date or date.today()

        if target_date in self.daily_stats:
            return self.daily_stats[target_date].realized_pnl

        # Calculate from closed trades
        daily_pnl = 0.0
        for position in self.closed_positions:
            if position.exit_timestamp and position.exit_timestamp.date() == target_date:
                daily_pnl += position.realized_pnl or 0.0

        return daily_pnl

    def get_todays_trades(self) -> List[Position]:
        """Get all trades closed today"""
        today = date.today()
        return [
            p for p in self.closed_positions
            if p.exit_timestamp and p.exit_timestamp.date() == today
        ]

    def get_consecutive_losses(self) -> int:
        """Count consecutive losing trades"""
        count = 0
        for position in reversed(self.closed_positions):
            if position.realized_pnl is None:
                continue

            if position.realized_pnl < 0:
                count += 1
            else:
                break

        return count

    def _update_daily_stats(self, position: Position) -> None:
        """Update daily statistics with closed position"""
        if not position.exit_timestamp or position.realized_pnl is None:
            return

        trade_date = position.exit_timestamp.date()

        if trade_date not in self.daily_stats:
            # Create new daily stats
            self.daily_stats[trade_date] = DailyStats(
                date=trade_date,
                starting_balance=self.current_balance - position.realized_pnl,
                ending_balance=self.current_balance,
                realized_pnl=position.realized_pnl,
                total_trades=1,
                winning_trades=1 if position.realized_pnl > 0 else 0,
                losing_trades=1 if position.realized_pnl < 0 else 0,
                largest_win=position.realized_pnl if position.realized_pnl > 0 else 0,
                largest_loss=position.realized_pnl if position.realized_pnl < 0 else 0,
                gross_profit=position.realized_pnl if position.realized_pnl > 0 else 0,
                gross_loss=abs(position.realized_pnl) if position.realized_pnl < 0 else 0
            )
        else:
            # Update existing stats
            stats = self.daily_stats[trade_date]
            stats.ending_balance = self.current_balance
            stats.realized_pnl += position.realized_pnl
            stats.total_trades += 1

            if position.realized_pnl > 0:
                stats.winning_trades += 1
                stats.gross_profit += position.realized_pnl
                stats.largest_win = max(stats.largest_win, position.realized_pnl)
            else:
                stats.losing_trades += 1
                stats.gross_loss += abs(position.realized_pnl)
                stats.largest_loss = min(stats.largest_loss, position.realized_pnl)

    def save_state(self) -> None:
        """Persist state to disk"""
        try:
            state = {
                'current_balance': self.current_balance,
                'open_positions': {
                    pid: pos.to_dict() for pid, pos in self.open_positions.items()
                },
                'closed_positions': [pos.to_dict() for pos in self.closed_positions[-100:]],  # Last 100
                'daily_stats': {
                    d.isoformat(): stats.to_dict()
                    for d, stats in self.daily_stats.items()
                },
                'last_updated': datetime.now().isoformat()
            }

            with open(self.state_file, 'w') as f:
                json.dump(state, f, indent=2)

            logger.debug(f"State saved to {self.state_file}")

        except Exception as e:
            logger.error(f"Failed to save state: {e}")

    def load_state(self) -> None:
        """Load persisted state from disk"""
        if not self.state_file.exists():
            logger.info("No persisted state found, starting fresh")
            return

        try:
            with open(self.state_file, 'r') as f:
                state = json.load(f)

            self.current_balance = state.get('current_balance', 10000.0)

            # Load open positions
            for pid, pos_data in state.get('open_positions', {}).items():
                self.open_positions[pid] = Position.from_dict(pos_data)

            # Load closed positions
            for pos_data in state.get('closed_positions', []):
                self.closed_positions.append(Position.from_dict(pos_data))

            # Load daily stats
            for date_str, stats_data in state.get('daily_stats', {}).items():
                self.daily_stats[date.fromisoformat(date_str)] = DailyStats.from_dict(stats_data)

            logger.info(
                f"State loaded from {self.state_file}. "
                f"Open: {len(self.open_positions)}, "
                f"Closed: {len(self.closed_positions)}"
            )

        except Exception as e:
            logger.error(f"Failed to load state: {e}")

    def get_state_summary(self) -> Dict[str, Any]:
        """Get summary of current state"""
        today_pnl = self.get_daily_pnl()
        today_trades = self.get_todays_trades()

        return {
            'current_balance': self.current_balance,
            'open_positions': len(self.open_positions),
            'portfolio_risk': self.get_total_portfolio_risk(),
            'today_pnl': today_pnl,
            'today_trades': len(today_trades),
            'consecutive_losses': self.get_consecutive_losses(),
            'total_closed_trades': len(self.closed_positions)
        }
