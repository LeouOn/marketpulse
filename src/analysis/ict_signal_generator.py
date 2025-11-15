"""
ICT Signal Generator

Combines ICT concepts with order flow analysis to generate high-probability trade signals.

Signal Types:
- FVG + CVD Confirmation
- Order Block Retest + Volume Spike
- Liquidity Sweep + Reversal
- Market Structure Break + Order Flow Confirmation
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Literal, Dict, Any
from datetime import datetime, timedelta
from loguru import logger

from .ict_concepts import (
    FairValueGap, OrderBlock, LiquidityPool, MarketStructure,
    FairValueGapDetector, OrderBlockIdentifier, LiquidityDetector, MarketStructureAnalyzer
)
from .order_flow import (
    VolumeBar, VolumeProfile, DeltaDivergence, Imbalance,
    CumulativeVolumeDeltaCalculator, VolumeDeltaAnalyzer, VolumeProfileBuilder
)


@dataclass
class ICTSignal:
    """Trading signal based on ICT concepts + order flow"""
    type: Literal["long", "short"]
    confidence: float  # 0-100
    entry_price: float
    stop_loss: float
    take_profit: List[float]  # Multiple TP levels
    timestamp: datetime

    # Signal reasoning
    trigger: str  # What triggered the signal
    ict_elements: List[str]  # ICT concepts involved
    order_flow_confirmation: str  # Order flow confirmation

    # Risk/Reward
    risk: float  # Distance to stop in points
    reward: float  # Distance to first TP in points
    risk_reward_ratio: float

    # Additional context
    market_structure: str  # bullish/bearish/ranging
    vix_regime: Optional[str] = None
    session: Optional[str] = None  # London/NewYork/Asian


@dataclass
class SignalConfluence:
    """Track confluence of multiple signals"""
    score: float  # 0-100
    elements: Dict[str, bool]  # Which elements are present
    strength: str  # weak/moderate/strong


class ICTSignalGenerator:
    """Generate trading signals using ICT + Order Flow"""

    def __init__(self, settings: Optional[Dict[str, Any]] = None):
        """
        Initialize signal generator

        Args:
            settings: Configuration dict with parameters
        """
        self.settings = settings or {}

        # Initialize ICT analyzers
        self.fvg_detector = FairValueGapDetector(
            min_gap_size=self.settings.get('min_fvg_size', 2.0)
        )
        self.ob_identifier = OrderBlockIdentifier(
            min_displacement=self.settings.get('min_displacement', 5.0)
        )
        self.liq_detector = LiquidityDetector()
        self.structure_analyzer = MarketStructureAnalyzer()

        # Initialize order flow analyzers
        self.cvd_calculator = CumulativeVolumeDeltaCalculator()
        self.delta_analyzer = VolumeDeltaAnalyzer()
        self.profile_builder = VolumeProfileBuilder()

        # Signal history
        self.signal_history: List[ICTSignal] = []

    def analyze_market(self, candles: pd.DataFrame) -> Dict[str, Any]:
        """
        Comprehensive market analysis using all ICT concepts

        Args:
            candles: OHLC candlestick data

        Returns:
            Dictionary with all ICT elements and order flow data
        """
        logger.info(f"Analyzing market with {len(candles)} candles")

        # ICT Concepts
        fvgs = self.fvg_detector.detect_fvgs(candles)
        order_blocks = self.ob_identifier.identify_order_blocks(candles)
        liquidity_pools = self.liq_detector.detect_liquidity_pools(candles)

        # Market Structure
        swing_highs, swing_lows = self.structure_analyzer.identify_swing_points(candles)
        market_structure = self.structure_analyzer.determine_structure(swing_highs, swing_lows)

        # Update states
        fvgs = self.fvg_detector.update_fvg_fills(fvgs, candles)
        order_blocks = self.ob_identifier.update_order_block_status(order_blocks, candles)
        liquidity_pools = self.liq_detector.detect_liquidity_sweeps(liquidity_pools, candles)

        # Order Flow (synthetic for now - would use real tick data)
        volume_profile = self.profile_builder.build_profile(candles)

        # Create synthetic CVD from candle data
        cvd_series = self._synthetic_cvd_from_candles(candles)

        return {
            'fvgs': fvgs,
            'order_blocks': order_blocks,
            'liquidity_pools': liquidity_pools,
            'market_structure': market_structure,
            'volume_profile': volume_profile,
            'cvd': cvd_series,
            'timestamp': datetime.now()
        }

    def generate_signals(
        self,
        candles: pd.DataFrame,
        market_analysis: Optional[Dict[str, Any]] = None
    ) -> List[ICTSignal]:
        """
        Generate trading signals from market analysis

        Args:
            candles: OHLC candlestick data
            market_analysis: Pre-computed market analysis (optional)

        Returns:
            List of ICTSignal objects
        """
        if market_analysis is None:
            market_analysis = self.analyze_market(candles)

        signals = []

        # Signal Type 1: FVG Fill + CVD Confirmation
        fvg_signals = self._generate_fvg_signals(
            candles,
            market_analysis['fvgs'],
            market_analysis['cvd'],
            market_analysis['market_structure']
        )
        signals.extend(fvg_signals)

        # Signal Type 2: Order Block Retest + Volume
        ob_signals = self._generate_order_block_signals(
            candles,
            market_analysis['order_blocks'],
            market_analysis['cvd'],
            market_analysis['market_structure']
        )
        signals.extend(ob_signals)

        # Signal Type 3: Liquidity Sweep + Reversal
        liq_signals = self._generate_liquidity_sweep_signals(
            candles,
            market_analysis['liquidity_pools'],
            market_analysis['cvd'],
            market_analysis['market_structure']
        )
        signals.extend(liq_signals)

        # Store signal history
        self.signal_history.extend(signals)

        logger.info(f"Generated {len(signals)} signals")
        return signals

    def _generate_fvg_signals(
        self,
        candles: pd.DataFrame,
        fvgs: List[FairValueGap],
        cvd: pd.Series,
        market_structure: MarketStructure
    ) -> List[ICTSignal]:
        """Generate signals from FVG fills"""
        signals = []

        current_price = candles.iloc[-1]['close']
        current_time = candles.index[-1]

        for fvg in fvgs:
            # Only trade FVGs that align with market structure
            if fvg.type == 'bullish' and market_structure.type != 'bullish':
                continue
            if fvg.type == 'bearish' and market_structure.type != 'bearish':
                continue

            # Check if FVG just filled (50%+)
            if fvg.filled and fvg.fill_timestamp:
                # Check if fill was recent (last 3 candles)
                time_since_fill = (current_time - fvg.fill_timestamp).total_seconds() / 60
                if time_since_fill > 15:  # More than 15 minutes ago
                    continue

                # Check CVD confirmation
                if len(cvd) > 0:
                    recent_cvd = cvd.iloc[-5:].mean() if len(cvd) >= 5 else cvd.iloc[-1]

                    cvd_confirms = (
                        (fvg.type == 'bullish' and recent_cvd > 0) or
                        (fvg.type == 'bearish' and recent_cvd < 0)
                    )

                    if cvd_confirms:
                        # Calculate confidence
                        confluence = self._calculate_confluence({
                            'fvg_filled': True,
                            'cvd_confirms': True,
                            'structure_aligned': True,
                            'volume_spike': candles.iloc[-1]['volume'] > candles['volume'].mean()
                        })

                        # Generate signal
                        if fvg.type == 'bullish':
                            entry = current_price
                            stop = fvg.lower - 2  # 2 points below FVG
                            tp1 = fvg.upper + (fvg.upper - fvg.lower)  # 1:1 R/R
                            tp2 = fvg.upper + 2 * (fvg.upper - fvg.lower)  # 1:2 R/R

                            risk = entry - stop
                            reward = tp1 - entry

                            signals.append(ICTSignal(
                                type='long',
                                confidence=confluence.score,
                                entry_price=entry,
                                stop_loss=stop,
                                take_profit=[tp1, tp2],
                                timestamp=current_time,
                                trigger='FVG_FILL',
                                ict_elements=['Bullish FVG', 'Market Structure Bullish'],
                                order_flow_confirmation=f'CVD: {recent_cvd:+.0f}',
                                risk=risk,
                                reward=reward,
                                risk_reward_ratio=reward / risk if risk > 0 else 0,
                                market_structure='bullish'
                            ))

                        else:  # bearish
                            entry = current_price
                            stop = fvg.upper + 2
                            tp1 = fvg.lower - (fvg.upper - fvg.lower)
                            tp2 = fvg.lower - 2 * (fvg.upper - fvg.lower)

                            risk = stop - entry
                            reward = entry - tp1

                            signals.append(ICTSignal(
                                type='short',
                                confidence=confluence.score,
                                entry_price=entry,
                                stop_loss=stop,
                                take_profit=[tp1, tp2],
                                timestamp=current_time,
                                trigger='FVG_FILL',
                                ict_elements=['Bearish FVG', 'Market Structure Bearish'],
                                order_flow_confirmation=f'CVD: {recent_cvd:+.0f}',
                                risk=risk,
                                reward=reward,
                                risk_reward_ratio=reward / risk if risk > 0 else 0,
                                market_structure='bearish'
                            ))

        return signals

    def _generate_order_block_signals(
        self,
        candles: pd.DataFrame,
        order_blocks: List[OrderBlock],
        cvd: pd.Series,
        market_structure: MarketStructure
    ) -> List[ICTSignal]:
        """Generate signals from Order Block retests"""
        signals = []

        current_price = candles.iloc[-1]['close']
        current_time = candles.index[-1]

        for ob in order_blocks:
            if ob.broken or not ob.tested:
                continue

            # Check if OB aligns with structure
            if ob.type == 'bullish' and market_structure.type != 'bullish':
                continue
            if ob.type == 'bearish' and market_structure.type != 'bearish':
                continue

            # Check if price is at OB
            at_ob = (
                (ob.type == 'bullish' and ob.low <= current_price <= ob.high) or
                (ob.type == 'bearish' and ob.low <= current_price <= ob.high)
            )

            if at_ob:
                # Check for volume spike (indicates interest)
                volume_spike = candles.iloc[-1]['volume'] > candles['volume'].mean() * 1.5

                if volume_spike:
                    recent_cvd = cvd.iloc[-5:].mean() if len(cvd) >= 5 else 0

                    confluence = self._calculate_confluence({
                        'order_block': True,
                        'volume_spike': True,
                        'structure_aligned': True,
                        'cvd_confirms': (
                            (ob.type == 'bullish' and recent_cvd > 0) or
                            (ob.type == 'bearish' and recent_cvd < 0)
                        )
                    })

                    if ob.type == 'bullish':
                        entry = current_price
                        stop = ob.low - 2
                        tp1 = entry + (entry - stop) * 1.5
                        tp2 = entry + (entry - stop) * 3

                        risk = entry - stop
                        reward = tp1 - entry

                        signals.append(ICTSignal(
                            type='long',
                            confidence=min(100, confluence.score + ob.strength * 0.2),
                            entry_price=entry,
                            stop_loss=stop,
                            take_profit=[tp1, tp2],
                            timestamp=current_time,
                            trigger='ORDER_BLOCK_RETEST',
                            ict_elements=['Bullish OB', 'Volume Spike'],
                            order_flow_confirmation=f'CVD: {recent_cvd:+.0f}, Vol Spike',
                            risk=risk,
                            reward=reward,
                            risk_reward_ratio=reward / risk if risk > 0 else 0,
                            market_structure='bullish'
                        ))

        return signals

    def _generate_liquidity_sweep_signals(
        self,
        candles: pd.DataFrame,
        liquidity_pools: List[LiquidityPool],
        cvd: pd.Series,
        market_structure: MarketStructure
    ) -> List[ICTSignal]:
        """Generate signals from liquidity sweeps"""
        signals = []

        current_time = candles.index[-1]

        for pool in liquidity_pools:
            if not pool.swept:
                continue

            # Check if sweep was recent
            if pool.sweep_timestamp:
                time_since_sweep = (current_time - pool.sweep_timestamp).total_seconds() / 60
                if time_since_sweep > 30:  # More than 30 minutes
                    continue

                # Liquidity sweep often precedes reversal
                # Buy-side sweep → expect down move
                # Sell-side sweep → expect up move

                if pool.type == 'sell_side' and market_structure.type == 'bullish':
                    # Sell-side liquidity swept, expect continuation up
                    current_price = candles.iloc[-1]['close']

                    entry = current_price
                    stop = pool.price - 3  # Below the swept level
                    tp1 = entry + (entry - stop) * 2
                    tp2 = entry + (entry - stop) * 3

                    risk = entry - stop
                    reward = tp1 - entry

                    recent_cvd = cvd.iloc[-5:].mean() if len(cvd) >= 5 else 0

                    confluence = self._calculate_confluence({
                        'liquidity_sweep': True,
                        'structure_aligned': True,
                        'cvd_confirms': recent_cvd > 0
                    })

                    signals.append(ICTSignal(
                        type='long',
                        confidence=min(100, confluence.score + pool.strength * 0.2),
                        entry_price=entry,
                        stop_loss=stop,
                        take_profit=[tp1, tp2],
                        timestamp=current_time,
                        trigger='LIQUIDITY_SWEEP',
                        ict_elements=['Sell-Side Liquidity Swept', 'Bullish Structure'],
                        order_flow_confirmation=f'CVD: {recent_cvd:+.0f}',
                        risk=risk,
                        reward=reward,
                        risk_reward_ratio=reward / risk if risk > 0 else 0,
                        market_structure='bullish'
                    ))

        return signals

    def _calculate_confluence(self, elements: Dict[str, bool]) -> SignalConfluence:
        """
        Calculate signal confluence score

        Args:
            elements: Dictionary of present elements

        Returns:
            SignalConfluence object
        """
        # Weight different elements
        weights = {
            'fvg_filled': 25,
            'order_block': 25,
            'liquidity_sweep': 20,
            'cvd_confirms': 20,
            'structure_aligned': 15,
            'volume_spike': 10
        }

        score = sum(weights.get(k, 10) for k, v in elements.items() if v)

        if score >= 70:
            strength = 'strong'
        elif score >= 50:
            strength = 'moderate'
        else:
            strength = 'weak'

        return SignalConfluence(
            score=min(100, score),
            elements=elements,
            strength=strength
        )

    def _synthetic_cvd_from_candles(self, candles: pd.DataFrame) -> pd.Series:
        """
        Create synthetic CVD from candle data (approximation)

        In production, would use real tick data

        Args:
            candles: OHLC data

        Returns:
            Synthetic CVD series
        """
        cvd_values = []
        cumulative = 0.0

        for idx, candle in candles.iterrows():
            # Approximate buy/sell volume from candle direction
            if candle['close'] > candle['open']:
                # Bullish candle - more buying
                buy_pct = 0.6
            else:
                # Bearish candle - more selling
                buy_pct = 0.4

            buy_vol = candle['volume'] * buy_pct
            sell_vol = candle['volume'] * (1 - buy_pct)

            delta = buy_vol - sell_vol
            cumulative += delta
            cvd_values.append(cumulative)

        return pd.Series(cvd_values, index=candles.index)
