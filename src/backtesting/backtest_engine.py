"""
Backtesting Engine

Run trading strategies on historical data to:
- Validate edge statistically
- Optimize parameters
- Calculate performance metrics
- Identify best setups and times
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass, field
from datetime import datetime, timedelta
from loguru import logger

from src.analysis.ict_signal_generator import ICTSignalGenerator
from src.analysis.divergence_detector import scan_for_divergences
from src.analysis.technical_indicators import TechnicalIndicators


@dataclass
class Trade:
    """Single trade result"""
    entry_time: datetime
    exit_time: datetime
    entry_price: float
    exit_price: float
    direction: str  # LONG or SHORT
    contracts: int
    pnl: float
    pnl_percent: float
    duration_minutes: int
    setup_type: str  # FVG, Order Block, Divergence, etc.
    win: bool

    # Additional metrics
    max_favorable_excursion: float = 0.0  # MFE
    max_adverse_excursion: float = 0.0     # MAE
    hour_of_day: int = 0
    day_of_week: int = 0
    cvd_at_entry: Optional[float] = None
    divergence_strength: Optional[float] = None


@dataclass
class BacktestResults:
    """Comprehensive backtest results"""
    # Basic metrics
    total_trades: int
    winning_trades: int
    losing_trades: int
    win_rate: float

    # P&L metrics
    total_pnl: float
    total_pnl_percent: float
    average_winner: float
    average_loser: float
    largest_winner: float
    largest_loser: float
    profit_factor: float  # gross_profit / gross_loss

    # Risk metrics
    max_drawdown: float
    max_drawdown_percent: float
    sharpe_ratio: float
    sortino_ratio: float

    # Trade metrics
    average_trade_duration: float  # minutes
    average_trade_pnl: float
    expectancy: float  # average $ per trade

    # Strategy-specific metrics
    fvg_success_rate: float
    divergence_success_rate: float
    best_hour_of_day: int
    worst_hour_of_day: int
    best_day_of_week: int

    # Performance by setup type
    performance_by_setup: Dict[str, Dict[str, float]] = field(default_factory=dict)

    # All trades
    trades: List[Trade] = field(default_factory=list)

    # Equity curve
    equity_curve: pd.DataFrame = field(default_factory=pd.DataFrame)


class Account:
    """Simulated trading account"""

    def __init__(self, initial_capital: float):
        self.initial_capital = initial_capital
        self.balance = initial_capital
        self.peak_balance = initial_capital
        self.max_drawdown = 0.0
        self.equity_curve = [initial_capital]
        self.timestamps = []

    def update(self, trade: Trade):
        """Update account after trade"""
        self.balance += trade.pnl

        # Track peak and drawdown
        if self.balance > self.peak_balance:
            self.peak_balance = self.balance

        current_drawdown = (self.peak_balance - self.balance) / self.peak_balance
        if current_drawdown > self.max_drawdown:
            self.max_drawdown = current_drawdown

        # Update equity curve
        self.equity_curve.append(self.balance)
        self.timestamps.append(trade.exit_time)

    def can_take_trade(self, signal: Dict[str, Any]) -> bool:
        """Check if we can take this trade"""
        # Simple check: do we have enough capital?
        required_margin = signal.get('required_margin', 1000)
        return self.balance >= required_margin


class SignalGenerator:
    """Generate trading signals from market data"""

    def generate_signal(
        self,
        fvgs: Dict[str, Any],
        divergences: Dict[str, Any],
        price: float,
        indicators: Dict[str, float],
        **kwargs
    ) -> Optional[Dict[str, Any]]:
        """
        Generate trading signal

        Args:
            fvgs: Fair Value Gaps
            divergences: Divergence analysis
            price: Current price
            indicators: Technical indicators

        Returns:
            Signal dict or None
        """
        # Check for bullish FVG + divergence combo
        if len(fvgs.get('bullish', [])) > 0 and divergences.get('signal') in ['BULLISH', 'STRONG_BULLISH']:
            fvg = fvgs['bullish'][0]

            # Check if price is near FVG
            if fvg['lower'] <= price <= fvg['upper'] * 1.01:
                return {
                    'direction': 'LONG',
                    'entry_price': price,
                    'stop_loss': fvg['lower'] - (fvg['upper'] - fvg['lower']) * 0.2,
                    'take_profit': price + (price - fvg['lower']) * 2,  # 1:2 R:R
                    'setup_type': 'FVG_BULLISH_DIVERGENCE',
                    'required_margin': 1000,
                    'divergence_strength': divergences.get('strongest', {}).get('strength', 0)
                }

        # Check for bearish FVG + divergence combo
        if len(fvgs.get('bearish', [])) > 0 and divergences.get('signal') in ['BEARISH', 'STRONG_BEARISH']:
            fvg = fvgs['bearish'][0]

            if fvg['lower'] * 0.99 <= price <= fvg['upper']:
                return {
                    'direction': 'SHORT',
                    'entry_price': price,
                    'stop_loss': fvg['upper'] + (fvg['upper'] - fvg['lower']) * 0.2,
                    'take_profit': price - (fvg['upper'] - price) * 2,
                    'setup_type': 'FVG_BEARISH_DIVERGENCE',
                    'required_margin': 1000,
                    'divergence_strength': divergences.get('strongest', {}).get('strength', 0)
                }

        return None


class BacktestEngine:
    """
    Backtesting engine for trading strategies

    Features:
    - Run strategies on historical data
    - Calculate comprehensive performance metrics
    - Analyze performance by setup type, time of day, etc.
    - Optimize parameters
    """

    def __init__(self):
        self.ict_analyzer = ICTSignalGenerator()
        self.signal_generator = SignalGenerator()

    def load_historical_data(
        self,
        symbol: str,
        start_date: str,
        end_date: str,
        interval: str = '5m'
    ) -> pd.DataFrame:
        """Load historical data"""
        logger.info(f"Loading historical data for {symbol} from {start_date} to {end_date}")

        try:
            from src.api.yahoo_client import YahooFinanceClient
            client = YahooFinanceClient()

            # Convert interval format
            yf_interval = {
                '1m': '1m',
                '5m': '5m',
                '15m': '15m',
                '1h': '1h',
                '1d': '1d'
            }.get(interval, '5m')

            # Calculate period
            start = pd.to_datetime(start_date)
            end = pd.to_datetime(end_date)
            days = (end - start).days

            if days <= 7:
                period = '7d'
            elif days <= 30:
                period = '1mo'
            elif days <= 90:
                period = '3mo'
            elif days <= 180:
                period = '6mo'
            else:
                period = '1y'

            df = client.get_historical_data(symbol, period=period, interval=yf_interval)

            # Filter to date range
            df = df.loc[start_date:end_date]

            logger.info(f"Loaded {len(df)} candles")
            return df

        except Exception as e:
            logger.error(f"Error loading historical data: {e}")
            # Return empty DataFrame
            return pd.DataFrame()

    def calculate_cvd(self, df: pd.DataFrame) -> pd.Series:
        """Calculate Cumulative Volume Delta (simplified)"""
        # Simplified CVD: positive when close > open, negative otherwise
        cvd = np.where(df['close'] > df['open'], df['volume'], -df['volume'])
        return pd.Series(cvd, index=df.index).cumsum()

    def execute_backtest_trade(
        self,
        signal: Dict[str, Any],
        candles: pd.DataFrame,
        entry_index: int,
        contracts: int
    ) -> Trade:
        """
        Simulate trade execution

        Args:
            signal: Trading signal
            candles: Historical candles
            entry_index: Index where trade entered
            contracts: Number of contracts

        Returns:
            Trade result
        """
        entry_time = candles.index[entry_index]
        entry_price = signal['entry_price']
        stop_loss = signal['stop_loss']
        take_profit = signal['take_profit']
        direction = signal['direction']

        # Track trade through candles
        max_favorable = 0.0
        max_adverse = 0.0

        # Look forward to find exit
        for i in range(entry_index + 1, min(entry_index + 100, len(candles))):  # Max 100 candles
            candle = candles.iloc[i]

            if direction == 'LONG':
                # Check for stop hit
                if candle['low'] <= stop_loss:
                    exit_price = stop_loss
                    exit_time = candles.index[i]
                    pnl = (exit_price - entry_price) * contracts * 20  # $20 per point for NQ
                    win = False
                    break

                # Check for target hit
                if candle['high'] >= take_profit:
                    exit_price = take_profit
                    exit_time = candles.index[i]
                    pnl = (exit_price - entry_price) * contracts * 20
                    win = True
                    break

                # Track MFE/MAE
                favorable = candle['high'] - entry_price
                adverse = entry_price - candle['low']
                max_favorable = max(max_favorable, favorable)
                max_adverse = max(max_adverse, adverse)

        else:
            # Trade not closed, close at last candle
            exit_price = candles.iloc[-1]['close']
            exit_time = candles.index[-1]
            pnl = (exit_price - entry_price) * contracts * 20
            win = pnl > 0

        # Calculate metrics
        duration = int((exit_time - entry_time).total_seconds() / 60)
        pnl_percent = (pnl / (entry_price * contracts * 20)) * 100

        return Trade(
            entry_time=entry_time,
            exit_time=exit_time,
            entry_price=entry_price,
            exit_price=exit_price,
            direction=direction,
            contracts=contracts,
            pnl=pnl,
            pnl_percent=pnl_percent,
            duration_minutes=duration,
            setup_type=signal['setup_type'],
            win=win,
            max_favorable_excursion=max_favorable,
            max_adverse_excursion=max_adverse,
            hour_of_day=entry_time.hour,
            day_of_week=entry_time.weekday(),
            divergence_strength=signal.get('divergence_strength')
        )

    def run_backtest(
        self,
        symbol: str = 'NQ',
        start_date: str = '2024-01-01',
        end_date: str = '2024-11-15',
        initial_capital: float = 10000,
        contracts: int = 1,
        interval: str = '5m'
    ) -> BacktestResults:
        """
        Run backtest on historical data

        Args:
            symbol: Symbol to trade
            start_date: Start date (YYYY-MM-DD)
            end_date: End date (YYYY-MM-DD)
            initial_capital: Starting capital
            contracts: Number of contracts per trade
            interval: Timeframe (5m, 15m, 1h, 1d)

        Returns:
            Comprehensive backtest results
        """
        logger.info(f"Starting backtest: {symbol} from {start_date} to {end_date}")

        # Load historical data
        candles = self.load_historical_data(symbol, start_date, end_date, interval)

        if candles.empty:
            logger.error("No historical data loaded")
            return BacktestResults(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                total_pnl_percent=0.0,
                average_winner=0.0,
                average_loser=0.0,
                largest_winner=0.0,
                largest_loser=0.0,
                profit_factor=0.0,
                max_drawdown=0.0,
                max_drawdown_percent=0.0,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                average_trade_duration=0.0,
                average_trade_pnl=0.0,
                expectancy=0.0,
                fvg_success_rate=0.0,
                divergence_success_rate=0.0,
                best_hour_of_day=0,
                worst_hour_of_day=0,
                best_day_of_week=0
            )

        # Initialize account
        account = Account(initial_capital)
        trades = []

        # Run backtest
        lookback = 100  # Need history for indicators

        for i in range(lookback, len(candles)):
            # Get window of data
            window = candles.iloc[i-lookback:i]

            # Detect FVGs
            fvg_list = self.ict_analyzer.fvg_detector.detect_fvgs(window)

            # Convert to dict format for SignalGenerator
            fvgs = {
                'bullish': [
                    {'lower': fvg.lower, 'upper': fvg.upper, 'size': fvg.size}
                    for fvg in fvg_list if fvg.type == 'bullish'
                ],
                'bearish': [
                    {'lower': fvg.lower, 'upper': fvg.upper, 'size': fvg.size}
                    for fvg in fvg_list if fvg.type == 'bearish'
                ]
            }

            # Detect divergences
            divergences = scan_for_divergences(window, min_strength=70.0)

            # Calculate indicators
            indicators_df = TechnicalIndicators.calculate_all(window)
            current_indicators = {
                'rsi': indicators_df['rsi'].iloc[-1] if 'rsi' in indicators_df else 50,
                'macd': indicators_df['macd'].iloc[-1] if 'macd' in indicators_df else 0,
            }

            # Generate signal
            signal = self.signal_generator.generate_signal(
                fvgs=fvgs,
                divergences=divergences,
                price=candles.iloc[i]['close'],
                indicators=current_indicators
            )

            # Execute trade if signal and account allows
            if signal and account.can_take_trade(signal):
                trade = self.execute_backtest_trade(signal, candles, i, contracts)
                trades.append(trade)
                account.update(trade)

                logger.debug(f"Trade executed: {trade.setup_type} {trade.direction} @ {trade.entry_price:.2f}, P&L: ${trade.pnl:.2f}")

        # Calculate results
        results = self._calculate_results(trades, account, initial_capital)

        logger.info(f"Backtest complete: {results.total_trades} trades, "
                   f"Win rate: {results.win_rate:.1f}%, "
                   f"Total P&L: ${results.total_pnl:.2f}")

        return results

    def _calculate_results(
        self,
        trades: List[Trade],
        account: Account,
        initial_capital: float
    ) -> BacktestResults:
        """Calculate comprehensive backtest results"""

        if not trades:
            return BacktestResults(
                total_trades=0,
                winning_trades=0,
                losing_trades=0,
                win_rate=0.0,
                total_pnl=0.0,
                total_pnl_percent=0.0,
                average_winner=0.0,
                average_loser=0.0,
                largest_winner=0.0,
                largest_loser=0.0,
                profit_factor=0.0,
                max_drawdown=account.max_drawdown,
                max_drawdown_percent=account.max_drawdown * 100,
                sharpe_ratio=0.0,
                sortino_ratio=0.0,
                average_trade_duration=0.0,
                average_trade_pnl=0.0,
                expectancy=0.0,
                fvg_success_rate=0.0,
                divergence_success_rate=0.0,
                best_hour_of_day=0,
                worst_hour_of_day=0,
                best_day_of_week=0
            )

        # Basic metrics
        total_trades = len(trades)
        winning_trades = sum(1 for t in trades if t.win)
        losing_trades = total_trades - winning_trades
        win_rate = (winning_trades / total_trades) * 100

        # P&L metrics
        total_pnl = sum(t.pnl for t in trades)
        total_pnl_percent = ((account.balance - initial_capital) / initial_capital) * 100

        winners = [t.pnl for t in trades if t.win]
        losers = [t.pnl for t in trades if not t.win]

        average_winner = np.mean(winners) if winners else 0
        average_loser = np.mean(losers) if losers else 0
        largest_winner = max(winners) if winners else 0
        largest_loser = min(losers) if losers else 0

        gross_profit = sum(winners) if winners else 0
        gross_loss = abs(sum(losers)) if losers else 1
        profit_factor = gross_profit / gross_loss if gross_loss > 0 else 0

        # Trade metrics
        average_trade_duration = np.mean([t.duration_minutes for t in trades])
        average_trade_pnl = total_pnl / total_trades
        expectancy = (win_rate/100 * average_winner) + ((1 - win_rate/100) * average_loser)

        # Sharpe ratio (simplified)
        returns = [t.pnl_percent for t in trades]
        sharpe_ratio = (np.mean(returns) / np.std(returns)) * np.sqrt(252) if np.std(returns) > 0 else 0

        # Sortino ratio (only negative deviations)
        negative_returns = [r for r in returns if r < 0]
        sortino_ratio = (np.mean(returns) / np.std(negative_returns)) * np.sqrt(252) if negative_returns and np.std(negative_returns) > 0 else 0

        # Strategy-specific metrics
        fvg_trades = [t for t in trades if 'FVG' in t.setup_type]
        fvg_success_rate = (sum(1 for t in fvg_trades if t.win) / len(fvg_trades) * 100) if fvg_trades else 0

        divergence_trades = [t for t in trades if 'DIVERGENCE' in t.setup_type]
        divergence_success_rate = (sum(1 for t in divergence_trades if t.win) / len(divergence_trades) * 100) if divergence_trades else 0

        # Best/worst hours
        hour_performance = {}
        for t in trades:
            if t.hour_of_day not in hour_performance:
                hour_performance[t.hour_of_day] = []
            hour_performance[t.hour_of_day].append(t.pnl)

        hour_avg = {h: np.mean(pnls) for h, pnls in hour_performance.items()}
        best_hour_of_day = max(hour_avg.items(), key=lambda x: x[1])[0] if hour_avg else 0
        worst_hour_of_day = min(hour_avg.items(), key=lambda x: x[1])[0] if hour_avg else 0

        # Best day of week
        day_performance = {}
        for t in trades:
            if t.day_of_week not in day_performance:
                day_performance[t.day_of_week] = []
            day_performance[t.day_of_week].append(t.pnl)

        day_avg = {d: np.mean(pnls) for d, pnls in day_performance.items()}
        best_day_of_week = max(day_avg.items(), key=lambda x: x[1])[0] if day_avg else 0

        # Performance by setup type
        setup_performance = {}
        for setup_type in set(t.setup_type for t in trades):
            setup_trades = [t for t in trades if t.setup_type == setup_type]
            setup_wins = sum(1 for t in setup_trades if t.win)
            setup_performance[setup_type] = {
                'total': len(setup_trades),
                'wins': setup_wins,
                'win_rate': (setup_wins / len(setup_trades)) * 100,
                'total_pnl': sum(t.pnl for t in setup_trades),
                'avg_pnl': np.mean([t.pnl for t in setup_trades])
            }

        # Create equity curve DataFrame
        equity_curve = pd.DataFrame({
            'timestamp': account.timestamps,
            'balance': account.equity_curve[1:]  # Skip initial balance
        })

        return BacktestResults(
            total_trades=total_trades,
            winning_trades=winning_trades,
            losing_trades=losing_trades,
            win_rate=win_rate,
            total_pnl=total_pnl,
            total_pnl_percent=total_pnl_percent,
            average_winner=average_winner,
            average_loser=average_loser,
            largest_winner=largest_winner,
            largest_loser=largest_loser,
            profit_factor=profit_factor,
            max_drawdown=account.max_drawdown,
            max_drawdown_percent=account.max_drawdown * 100,
            sharpe_ratio=sharpe_ratio,
            sortino_ratio=sortino_ratio,
            average_trade_duration=average_trade_duration,
            average_trade_pnl=average_trade_pnl,
            expectancy=expectancy,
            fvg_success_rate=fvg_success_rate,
            divergence_success_rate=divergence_success_rate,
            best_hour_of_day=best_hour_of_day,
            worst_hour_of_day=worst_hour_of_day,
            best_day_of_week=best_day_of_week,
            performance_by_setup=setup_performance,
            trades=trades,
            equity_curve=equity_curve
        )
