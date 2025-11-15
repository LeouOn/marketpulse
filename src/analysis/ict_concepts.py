"""
ICT (Inner Circle Trader) Concepts Implementation

This module implements core ICT concepts including:
- Fair Value Gaps (FVG)
- Order Blocks (OB)
- Liquidity Pools
- Break of Structure (BOS)
- Change of Character (CHoCH)
- Displacement
- Market Structure Breaks (MSB)
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Literal, Tuple
from datetime import datetime
from loguru import logger


@dataclass
class FairValueGap:
    """Fair Value Gap - imbalance in price action"""
    type: Literal["bullish", "bearish"]
    upper: float  # Top of the gap
    lower: float  # Bottom of the gap
    size: float   # Gap size in points
    timestamp: datetime
    candle_index: int
    filled: bool = False
    fill_percentage: float = 0.0
    fill_timestamp: Optional[datetime] = None

    def midpoint(self) -> float:
        """Get gap midpoint"""
        return (self.upper + self.lower) / 2

    def is_valid(self) -> bool:
        """Check if gap is still valid (not fully filled)"""
        return not self.filled and self.fill_percentage < 100


@dataclass
class OrderBlock:
    """Order Block - area where smart money placed orders"""
    type: Literal["bullish", "bearish"]
    high: float
    low: float
    open: float
    close: float
    timestamp: datetime
    candle_index: int
    volume: float
    strength: float  # 0-100 score
    tested: bool = False
    broken: bool = False

    def midpoint(self) -> float:
        """Get OB midpoint"""
        return (self.high + self.low) / 2

    def is_valid(self) -> bool:
        """Check if OB is still valid (not broken)"""
        return not self.broken


@dataclass
class LiquidityPool:
    """Liquidity Pool - areas where stops likely sit"""
    type: Literal["buy_side", "sell_side"]  # Buy-side = above, Sell-side = below
    price: float
    timestamp: datetime
    strength: float  # Based on swing high/low significance
    swept: bool = False
    sweep_timestamp: Optional[datetime] = None


@dataclass
class MarketStructure:
    """Market Structure - Higher Highs, Higher Lows, etc."""
    type: Literal["bullish", "bearish", "ranging"]
    swing_highs: List[Tuple[datetime, float]]
    swing_lows: List[Tuple[datetime, float]]
    last_bos: Optional[datetime] = None  # Break of Structure
    last_choch: Optional[datetime] = None  # Change of Character


class FairValueGapDetector:
    """Detect Fair Value Gaps in price action"""

    def __init__(self, min_gap_size: float = 2.0):
        """
        Initialize FVG detector

        Args:
            min_gap_size: Minimum gap size in points (e.g., 2 points for NQ)
        """
        self.min_gap_size = min_gap_size

    def detect_fvgs(self, candles: pd.DataFrame) -> List[FairValueGap]:
        """
        Detect all Fair Value Gaps in candlestick data

        FVG Formation:
        - Bullish FVG: candle[i-2].high < candle[i].low (gap between them)
        - Bearish FVG: candle[i-2].low > candle[i].high

        Middle candle (i-1) is the "imbalance" candle

        Args:
            candles: DataFrame with OHLC data

        Returns:
            List of detected FVGs
        """
        fvgs = []

        if len(candles) < 3:
            return fvgs

        for i in range(2, len(candles)):
            candle_prev2 = candles.iloc[i-2]
            candle_current = candles.iloc[i]

            # Bullish FVG: gap between candle[i-2].high and candle[i].low
            if candle_prev2['high'] < candle_current['low']:
                gap_size = candle_current['low'] - candle_prev2['high']

                if gap_size >= self.min_gap_size:
                    fvgs.append(FairValueGap(
                        type='bullish',
                        upper=candle_current['low'],
                        lower=candle_prev2['high'],
                        size=gap_size,
                        timestamp=candle_current.name,
                        candle_index=i
                    ))

            # Bearish FVG: gap between candle[i-2].low and candle[i].high
            elif candle_prev2['low'] > candle_current['high']:
                gap_size = candle_prev2['low'] - candle_current['high']

                if gap_size >= self.min_gap_size:
                    fvgs.append(FairValueGap(
                        type='bearish',
                        upper=candle_prev2['low'],
                        lower=candle_current['high'],
                        size=gap_size,
                        timestamp=candle_current.name,
                        candle_index=i
                    ))

        logger.info(f"Detected {len(fvgs)} FVGs ({sum(1 for f in fvgs if f.type == 'bullish')} bullish, {sum(1 for f in fvgs if f.type == 'bearish')} bearish)")
        return fvgs

    def update_fvg_fills(self, fvgs: List[FairValueGap], current_candles: pd.DataFrame) -> List[FairValueGap]:
        """
        Update FVG fill status based on current price action

        Args:
            fvgs: List of FVGs to check
            current_candles: Recent candlestick data

        Returns:
            Updated list of FVGs
        """
        for fvg in fvgs:
            if fvg.filled:
                continue

            # Get candles after FVG formation
            candles_after = current_candles[current_candles.index > fvg.timestamp]

            if candles_after.empty:
                continue

            for idx, candle in candles_after.iterrows():
                if fvg.type == 'bullish':
                    # Check if price came back down into the gap
                    if candle['low'] <= fvg.upper:
                        # Calculate fill percentage
                        lowest_price_in_gap = min(candle['low'], fvg.upper)
                        fill_amount = fvg.upper - lowest_price_in_gap
                        fvg.fill_percentage = min(100, (fill_amount / fvg.size) * 100)

                        # 50% fill is considered "filled" for trading purposes
                        if fvg.fill_percentage >= 50 and not fvg.filled:
                            fvg.filled = True
                            fvg.fill_timestamp = idx
                            logger.debug(f"Bullish FVG filled at {idx}: {fvg.fill_percentage:.1f}%")

                else:  # bearish
                    # Check if price came back up into the gap
                    if candle['high'] >= fvg.lower:
                        highest_price_in_gap = max(candle['high'], fvg.lower)
                        fill_amount = highest_price_in_gap - fvg.lower
                        fvg.fill_percentage = min(100, (fill_amount / fvg.size) * 100)

                        if fvg.fill_percentage >= 50 and not fvg.filled:
                            fvg.filled = True
                            fvg.fill_timestamp = idx
                            logger.debug(f"Bearish FVG filled at {idx}: {fvg.fill_percentage:.1f}%")

        return fvgs


class OrderBlockIdentifier:
    """Identify Order Blocks - areas where smart money placed orders"""

    def __init__(self, min_displacement: float = 5.0):
        """
        Initialize Order Block identifier

        Args:
            min_displacement: Minimum price displacement in points to qualify as OB
        """
        self.min_displacement = min_displacement

    def identify_order_blocks(self, candles: pd.DataFrame) -> List[OrderBlock]:
        """
        Identify Order Blocks in price action

        Order Block = last opposite-colored candle before strong displacement

        Bullish OB:
        - Last down candle before strong move up
        - Often has high volume

        Bearish OB:
        - Last up candle before strong move down

        Args:
            candles: DataFrame with OHLC data

        Returns:
            List of identified Order Blocks
        """
        order_blocks = []

        if len(candles) < 3:
            return order_blocks

        for i in range(1, len(candles) - 1):
            candle = candles.iloc[i]
            next_candle = candles.iloc[i + 1]

            # Bullish OB: down candle followed by strong up move
            if candle['close'] < candle['open']:  # Down candle
                displacement = next_candle['close'] - next_candle['open']

                if displacement >= self.min_displacement:
                    # Calculate strength based on volume and displacement
                    volume_strength = min(100, (candle['volume'] / candles['volume'].mean()) * 50)
                    displacement_strength = min(50, (displacement / self.min_displacement) * 50)
                    strength = volume_strength + displacement_strength

                    order_blocks.append(OrderBlock(
                        type='bullish',
                        high=candle['high'],
                        low=candle['low'],
                        open=candle['open'],
                        close=candle['close'],
                        timestamp=candle.name,
                        candle_index=i,
                        volume=candle['volume'],
                        strength=min(100, strength)
                    ))

            # Bearish OB: up candle followed by strong down move
            elif candle['close'] > candle['open']:  # Up candle
                displacement = candle['close'] - next_candle['close']

                if displacement >= self.min_displacement:
                    volume_strength = min(100, (candle['volume'] / candles['volume'].mean()) * 50)
                    displacement_strength = min(50, (displacement / self.min_displacement) * 50)
                    strength = volume_strength + displacement_strength

                    order_blocks.append(OrderBlock(
                        type='bearish',
                        high=candle['high'],
                        low=candle['low'],
                        open=candle['open'],
                        close=candle['close'],
                        timestamp=candle.name,
                        candle_index=i,
                        volume=candle['volume'],
                        strength=min(100, strength)
                    ))

        logger.info(f"Identified {len(order_blocks)} Order Blocks")
        return order_blocks

    def update_order_block_status(
        self,
        order_blocks: List[OrderBlock],
        current_candles: pd.DataFrame
    ) -> List[OrderBlock]:
        """
        Update Order Block status (tested/broken)

        Args:
            order_blocks: List of OBs to check
            current_candles: Recent candlestick data

        Returns:
            Updated list of Order Blocks
        """
        for ob in order_blocks:
            if ob.broken:
                continue

            candles_after = current_candles[current_candles.index > ob.timestamp]

            if candles_after.empty:
                continue

            for idx, candle in candles_after.iterrows():
                if ob.type == 'bullish':
                    # OB is tested if price comes back to it
                    if candle['low'] <= ob.high and candle['low'] >= ob.low:
                        ob.tested = True

                    # OB is broken if price closes below it
                    if candle['close'] < ob.low:
                        ob.broken = True
                        logger.debug(f"Bullish OB broken at {idx}")
                        break

                else:  # bearish
                    if candle['high'] >= ob.low and candle['high'] <= ob.high:
                        ob.tested = True

                    if candle['close'] > ob.high:
                        ob.broken = True
                        logger.debug(f"Bearish OB broken at {idx}")
                        break

        return order_blocks


class LiquidityDetector:
    """Detect liquidity pools - areas where stops likely sit"""

    def detect_liquidity_pools(
        self,
        candles: pd.DataFrame,
        lookback: int = 50
    ) -> List[LiquidityPool]:
        """
        Detect liquidity pools at swing highs and lows

        Buy-side liquidity = above swing highs (long stops)
        Sell-side liquidity = below swing lows (short stops)

        Args:
            candles: DataFrame with OHLC data
            lookback: Number of candles to look back for swings

        Returns:
            List of identified liquidity pools
        """
        liquidity_pools = []

        if len(candles) < lookback:
            return liquidity_pools

        # Find swing highs (buy-side liquidity)
        for i in range(lookback, len(candles) - lookback):
            window = candles.iloc[i-lookback:i+lookback+1]
            current = candles.iloc[i]

            # Swing high: highest point in window
            if current['high'] == window['high'].max():
                # Calculate strength based on how many times it's been tested
                touches = sum(1 for h in window['high'] if abs(h - current['high']) < 1.0)
                strength = min(100, touches * 20)

                liquidity_pools.append(LiquidityPool(
                    type='buy_side',
                    price=current['high'],
                    timestamp=current.name,
                    strength=strength
                ))

            # Swing low: lowest point in window
            if current['low'] == window['low'].min():
                touches = sum(1 for l in window['low'] if abs(l - current['low']) < 1.0)
                strength = min(100, touches * 20)

                liquidity_pools.append(LiquidityPool(
                    type='sell_side',
                    price=current['low'],
                    timestamp=current.name,
                    strength=strength
                ))

        logger.info(f"Detected {len(liquidity_pools)} liquidity pools")
        return liquidity_pools

    def detect_liquidity_sweeps(
        self,
        liquidity_pools: List[LiquidityPool],
        current_candles: pd.DataFrame
    ) -> List[LiquidityPool]:
        """
        Detect when liquidity pools have been swept

        Sweep = price briefly goes beyond the level then reverses

        Args:
            liquidity_pools: List of liquidity pools
            current_candles: Recent candlestick data

        Returns:
            Updated list of liquidity pools
        """
        for pool in liquidity_pools:
            if pool.swept:
                continue

            candles_after = current_candles[current_candles.index > pool.timestamp]

            for idx, candle in candles_after.iterrows():
                if pool.type == 'buy_side':
                    # Buy-side swept if high goes above the level
                    if candle['high'] > pool.price:
                        pool.swept = True
                        pool.sweep_timestamp = idx
                        logger.debug(f"Buy-side liquidity swept at {idx}: ${pool.price:.2f}")
                        break

                else:  # sell_side
                    # Sell-side swept if low goes below the level
                    if candle['low'] < pool.price:
                        pool.swept = True
                        pool.sweep_timestamp = idx
                        logger.debug(f"Sell-side liquidity swept at {idx}: ${pool.price:.2f}")
                        break

        return liquidity_pools


class MarketStructureAnalyzer:
    """Analyze market structure - BOS, CHoCH, MSB"""

    def __init__(self, swing_lookback: int = 10):
        """
        Initialize market structure analyzer

        Args:
            swing_lookback: Number of candles for swing point identification
        """
        self.swing_lookback = swing_lookback

    def identify_swing_points(
        self,
        candles: pd.DataFrame
    ) -> Tuple[List[Tuple[datetime, float]], List[Tuple[datetime, float]]]:
        """
        Identify swing highs and swing lows

        Returns:
            Tuple of (swing_highs, swing_lows)
        """
        swing_highs = []
        swing_lows = []

        for i in range(self.swing_lookback, len(candles) - self.swing_lookback):
            window = candles.iloc[i-self.swing_lookback:i+self.swing_lookback+1]
            current = candles.iloc[i]

            # Swing high
            if current['high'] == window['high'].max():
                swing_highs.append((current.name, current['high']))

            # Swing low
            if current['low'] == window['low'].min():
                swing_lows.append((current.name, current['low']))

        return swing_highs, swing_lows

    def determine_structure(
        self,
        swing_highs: List[Tuple[datetime, float]],
        swing_lows: List[Tuple[datetime, float]]
    ) -> MarketStructure:
        """
        Determine overall market structure

        Bullish: Higher Highs + Higher Lows
        Bearish: Lower Highs + Lower Lows
        Ranging: Mixed or sideways

        Returns:
            MarketStructure object
        """
        if len(swing_highs) < 2 or len(swing_lows) < 2:
            return MarketStructure(
                type='ranging',
                swing_highs=swing_highs,
                swing_lows=swing_lows
            )

        # Check last 3 swings
        recent_highs = swing_highs[-3:] if len(swing_highs) >= 3 else swing_highs
        recent_lows = swing_lows[-3:] if len(swing_lows) >= 3 else swing_lows

        # Higher Highs?
        higher_highs = all(
            recent_highs[i][1] > recent_highs[i-1][1]
            for i in range(1, len(recent_highs))
        )

        # Higher Lows?
        higher_lows = all(
            recent_lows[i][1] > recent_lows[i-1][1]
            for i in range(1, len(recent_lows))
        )

        # Lower Highs?
        lower_highs = all(
            recent_highs[i][1] < recent_highs[i-1][1]
            for i in range(1, len(recent_highs))
        )

        # Lower Lows?
        lower_lows = all(
            recent_lows[i][1] < recent_lows[i-1][1]
            for i in range(1, len(recent_lows))
        )

        # Determine structure
        if higher_highs and higher_lows:
            structure_type = 'bullish'
        elif lower_highs and lower_lows:
            structure_type = 'bearish'
        else:
            structure_type = 'ranging'

        return MarketStructure(
            type=structure_type,
            swing_highs=swing_highs,
            swing_lows=swing_lows
        )

    def detect_break_of_structure(
        self,
        candles: pd.DataFrame,
        market_structure: MarketStructure
    ) -> Optional[datetime]:
        """
        Detect Break of Structure (BOS)

        BOS in uptrend: Price breaks above previous swing high
        BOS in downtrend: Price breaks below previous swing low

        Returns:
            Timestamp of BOS or None
        """
        if not market_structure.swing_highs or not market_structure.swing_lows:
            return None

        latest_candle = candles.iloc[-1]

        if market_structure.type == 'bullish':
            # Check if we broke above previous swing high
            if market_structure.swing_highs:
                prev_high = market_structure.swing_highs[-1][1]
                if latest_candle['close'] > prev_high:
                    return latest_candle.name

        elif market_structure.type == 'bearish':
            # Check if we broke below previous swing low
            if market_structure.swing_lows:
                prev_low = market_structure.swing_lows[-1][1]
                if latest_candle['close'] < prev_low:
                    return latest_candle.name

        return None
