"""
Order Flow Analysis Module

Implements real-time order flow analysis including:
- Cumulative Volume Delta (CVD)
- Volume Profile (VPOC, VAH, VAL)
- Delta Divergence Detection
- Absorption and Exhaustion
- Imbalance Detection
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Dict, Literal, Tuple
from datetime import datetime
from loguru import logger


@dataclass
class VolumeBar:
    """Volume bar with buy/sell breakdown"""
    timestamp: datetime
    buy_volume: float
    sell_volume: float
    total_volume: float
    delta: float  # buy_volume - sell_volume
    delta_percent: float  # delta / total_volume * 100

    @classmethod
    def from_trades(cls, timestamp: datetime, trades: List[dict]) -> 'VolumeBar':
        """Create VolumeBar from list of trades"""
        buy_vol = sum(t['volume'] for t in trades if t['side'] == 'buy')
        sell_vol = sum(t['volume'] for t in trades if t['side'] == 'sell')
        total_vol = buy_vol + sell_vol

        return cls(
            timestamp=timestamp,
            buy_volume=buy_vol,
            sell_volume=sell_vol,
            total_volume=total_vol,
            delta=buy_vol - sell_vol,
            delta_percent=(buy_vol - sell_vol) / total_vol * 100 if total_vol > 0 else 0
        )


@dataclass
class VolumeProfileLevel:
    """Single price level in volume profile"""
    price: float
    volume: float
    buy_volume: float
    sell_volume: float
    delta: float


@dataclass
class VolumeProfile:
    """Complete volume profile for a period"""
    levels: List[VolumeProfileLevel]
    poc: float  # Point of Control (highest volume)
    vah: float  # Value Area High (70% volume)
    val: float  # Value Area Low (70% volume)
    total_volume: float


@dataclass
class DeltaDivergence:
    """Delta divergence signal"""
    type: Literal["bullish", "bearish"]
    timestamp: datetime
    price_at_signal: float
    delta_at_signal: float
    strength: float  # 0-100


@dataclass
class Imbalance:
    """Order flow imbalance"""
    type: Literal["buy", "sell"]
    price: float
    timestamp: datetime
    ratio: float  # Imbalance ratio (e.g., 3:1)
    strength: float


class CumulativeVolumeDeltaCalculator:
    """Calculate and track Cumulative Volume Delta (CVD)"""

    def __init__(self):
        """Initialize CVD calculator"""
        self.cvd_history: List[Tuple[datetime, float]] = []
        self.running_cvd = 0.0

    def calculate_cvd(self, volume_bars: List[VolumeBar]) -> pd.Series:
        """
        Calculate cumulative volume delta from volume bars

        CVD = Sum of (Buy Volume - Sell Volume)

        Args:
            volume_bars: List of VolumeBar objects

        Returns:
            Pandas Series with CVD values
        """
        if not volume_bars:
            return pd.Series()

        cvd_values = []
        cumulative = 0.0

        for bar in volume_bars:
            cumulative += bar.delta
            cvd_values.append(cumulative)

        timestamps = [bar.timestamp for bar in volume_bars]
        return pd.Series(cvd_values, index=timestamps)

    def update_cvd(self, new_bar: VolumeBar) -> float:
        """
        Update running CVD with new bar

        Args:
            new_bar: New VolumeBar

        Returns:
            Updated CVD value
        """
        self.running_cvd += new_bar.delta
        self.cvd_history.append((new_bar.timestamp, self.running_cvd))
        return self.running_cvd

    def get_cvd_slope(self, lookback: int = 10) -> float:
        """
        Calculate CVD slope (trend strength)

        Positive slope = buying pressure
        Negative slope = selling pressure

        Args:
            lookback: Number of bars to analyze

        Returns:
            CVD slope
        """
        if len(self.cvd_history) < lookback:
            return 0.0

        recent = self.cvd_history[-lookback:]
        x = np.arange(len(recent))
        y = np.array([cvd for _, cvd in recent])

        # Linear regression
        coeffs = np.polyfit(x, y, 1)
        return coeffs[0]  # Slope


class VolumeDeltaAnalyzer:
    """Analyze volume delta for divergences and patterns"""

    def detect_delta_divergence(
        self,
        price: pd.Series,
        cvd: pd.Series,
        lookback: int = 20
    ) -> Optional[DeltaDivergence]:
        """
        Detect bullish/bearish divergence between price and CVD

        Bullish Divergence:
        - Price making lower lows
        - CVD making higher lows (accumulation)

        Bearish Divergence:
        - Price making higher highs
        - CVD making lower highs (distribution)

        Args:
            price: Price series
            cvd: CVD series
            lookback: Bars to look back

        Returns:
            DeltaDivergence if found, None otherwise
        """
        if len(price) < lookback or len(cvd) < lookback:
            return None

        recent_price = price.iloc[-lookback:]
        recent_cvd = cvd.iloc[-lookback:]

        # Find price lows and highs
        price_lows = self._find_local_minimums(recent_price)
        price_highs = self._find_local_maximums(recent_price)

        # Find CVD lows and highs
        cvd_lows = self._find_local_minimums(recent_cvd)
        cvd_highs = self._find_local_maximums(recent_cvd)

        # Check for bullish divergence (price lower low, CVD higher low)
        if len(price_lows) >= 2 and len(cvd_lows) >= 2:
            if price_lows[-1] < price_lows[-2] and cvd_lows[-1] > cvd_lows[-2]:
                strength = abs(cvd_lows[-1] - cvd_lows[-2]) / abs(price_lows[-1] - price_lows[-2])
                strength = min(100, strength * 10)

                return DeltaDivergence(
                    type='bullish',
                    timestamp=price.index[-1],
                    price_at_signal=price.iloc[-1],
                    delta_at_signal=cvd.iloc[-1],
                    strength=strength
                )

        # Check for bearish divergence (price higher high, CVD lower high)
        if len(price_highs) >= 2 and len(cvd_highs) >= 2:
            if price_highs[-1] > price_highs[-2] and cvd_highs[-1] < cvd_highs[-2]:
                strength = abs(cvd_highs[-2] - cvd_highs[-1]) / abs(price_highs[-1] - price_highs[-2])
                strength = min(100, strength * 10)

                return DeltaDivergence(
                    type='bearish',
                    timestamp=price.index[-1],
                    price_at_signal=price.iloc[-1],
                    delta_at_signal=cvd.iloc[-1],
                    strength=strength
                )

        return None

    def _find_local_minimums(self, series: pd.Series, window: int = 3) -> List[float]:
        """Find local minimums in series"""
        minimums = []
        for i in range(window, len(series) - window):
            if series.iloc[i] == series.iloc[i-window:i+window+1].min():
                minimums.append(series.iloc[i])
        return minimums

    def _find_local_maximums(self, series: pd.Series, window: int = 3) -> List[float]:
        """Find local maximums in series"""
        maximums = []
        for i in range(window, len(series) - window):
            if series.iloc[i] == series.iloc[i-window:i+window+1].max():
                maximums.append(series.iloc[i])
        return maximums


class VolumeProfileBuilder:
    """Build volume profile from price/volume data"""

    def __init__(self, price_tick: float = 0.25):
        """
        Initialize volume profile builder

        Args:
            price_tick: Price tick size (e.g., 0.25 for NQ)
        """
        self.price_tick = price_tick

    def build_profile(
        self,
        candles: pd.DataFrame,
        value_area_pct: float = 70.0
    ) -> VolumeProfile:
        """
        Build volume profile from candlestick data

        Args:
            candles: DataFrame with OHLC + Volume
            value_area_pct: Percentage for value area (default 70%)

        Returns:
            VolumeProfile object
        """
        if candles.empty:
            return VolumeProfile(
                levels=[],
                poc=0.0,
                vah=0.0,
                val=0.0,
                total_volume=0.0
            )

        # Create price levels
        min_price = candles['low'].min()
        max_price = candles['high'].max()

        # Round to tick size
        min_price = np.floor(min_price / self.price_tick) * self.price_tick
        max_price = np.ceil(max_price / self.price_tick) * self.price_tick

        price_levels = np.arange(min_price, max_price + self.price_tick, self.price_tick)

        # Build volume at each price level
        volume_at_price = {}

        for price in price_levels:
            volume_at_price[price] = {
                'total': 0.0,
                'buy': 0.0,
                'sell': 0.0
            }

        # Distribute volume across price range
        for idx, candle in candles.iterrows():
            # Simple distribution: spread volume evenly across candle range
            candle_range = candle['high'] - candle['low']
            if candle_range == 0:
                candle_range = self.price_tick

            volume_per_tick = candle['volume'] / (candle_range / self.price_tick)

            # Add volume to each price level in candle
            for price in price_levels:
                if candle['low'] <= price <= candle['high']:
                    volume_at_price[price]['total'] += volume_per_tick

                    # Estimate buy/sell (simplified - bullish candle = more buying at top)
                    if candle['close'] > candle['open']:  # Bullish
                        if price > (candle['low'] + candle_range / 2):
                            volume_at_price[price]['buy'] += volume_per_tick * 0.6
                            volume_at_price[price]['sell'] += volume_per_tick * 0.4
                        else:
                            volume_at_price[price]['buy'] += volume_per_tick * 0.4
                            volume_at_price[price]['sell'] += volume_per_tick * 0.6
                    else:  # Bearish
                        if price < (candle['low'] + candle_range / 2):
                            volume_at_price[price]['sell'] += volume_per_tick * 0.6
                            volume_at_price[price]['buy'] += volume_per_tick * 0.4
                        else:
                            volume_at_price[price]['sell'] += volume_per_tick * 0.4
                            volume_at_price[price]['buy'] += volume_per_tick * 0.6

        # Create VolumeProfileLevel objects
        levels = []
        for price in sorted(volume_at_price.keys()):
            vol_data = volume_at_price[price]
            if vol_data['total'] > 0:
                levels.append(VolumeProfileLevel(
                    price=price,
                    volume=vol_data['total'],
                    buy_volume=vol_data['buy'],
                    sell_volume=vol_data['sell'],
                    delta=vol_data['buy'] - vol_data['sell']
                ))

        # Find POC (Point of Control - highest volume)
        if levels:
            poc_level = max(levels, key=lambda x: x.volume)
            poc = poc_level.price
        else:
            poc = (min_price + max_price) / 2

        # Calculate Value Area (70% of volume)
        total_vol = sum(level.volume for level in levels)

        if levels:
            # Sort by volume
            sorted_levels = sorted(levels, key=lambda x: x.volume, reverse=True)

            # Find levels that account for value_area_pct of volume
            value_area_vol = 0.0
            value_area_prices = []

            for level in sorted_levels:
                value_area_vol += level.volume
                value_area_prices.append(level.price)

                if value_area_vol >= (total_vol * value_area_pct / 100):
                    break

            vah = max(value_area_prices)
            val = min(value_area_prices)
        else:
            vah = max_price
            val = min_price

        return VolumeProfile(
            levels=levels,
            poc=poc,
            vah=vah,
            val=val,
            total_volume=total_vol
        )


class ImbalanceDetector:
    """Detect order flow imbalances"""

    def __init__(self, imbalance_ratio: float = 3.0):
        """
        Initialize imbalance detector

        Args:
            imbalance_ratio: Ratio to qualify as imbalance (e.g., 3:1)
        """
        self.imbalance_ratio = imbalance_ratio

    def detect_imbalances(
        self,
        volume_bars: List[VolumeBar],
        lookback: int = 5
    ) -> List[Imbalance]:
        """
        Detect order flow imbalances

        Imbalance = extreme buy or sell pressure at a price level

        Args:
            volume_bars: List of VolumeBar objects
            lookback: Number of bars to analyze

        Returns:
            List of detected imbalances
        """
        imbalances = []

        if len(volume_bars) < lookback:
            return imbalances

        for i in range(len(volume_bars) - lookback + 1):
            window = volume_bars[i:i+lookback]

            total_buy = sum(bar.buy_volume for bar in window)
            total_sell = sum(bar.sell_volume for bar in window)

            # Check for buy imbalance
            if total_buy > 0 and total_sell > 0:
                buy_ratio = total_buy / total_sell

                if buy_ratio >= self.imbalance_ratio:
                    strength = min(100, (buy_ratio / self.imbalance_ratio) * 50)

                    imbalances.append(Imbalance(
                        type='buy',
                        price=0.0,  # Price would come from actual bar data
                        timestamp=window[-1].timestamp,
                        ratio=buy_ratio,
                        strength=strength
                    ))

            # Check for sell imbalance
            if total_sell > 0 and total_buy > 0:
                sell_ratio = total_sell / total_buy

                if sell_ratio >= self.imbalance_ratio:
                    strength = min(100, (sell_ratio / self.imbalance_ratio) * 50)

                    imbalances.append(Imbalance(
                        type='sell',
                        price=0.0,
                        timestamp=window[-1].timestamp,
                        ratio=sell_ratio,
                        strength=strength
                    ))

        return imbalances


class AbsorptionDetector:
    """Detect absorption (large volume with little price movement)"""

    def detect_absorption(
        self,
        candles: pd.DataFrame,
        volume_threshold_multiplier: float = 2.0,
        price_change_threshold: float = 0.5
    ) -> List[Tuple[datetime, str]]:
        """
        Detect absorption events

        Absorption = high volume but small price change
        Indicates large orders being absorbed

        Args:
            candles: DataFrame with OHLC + Volume
            volume_threshold_multiplier: Volume must be X times average
            price_change_threshold: Max price change percentage

        Returns:
            List of (timestamp, type) tuples
        """
        absorption_events = []

        if len(candles) < 20:
            return absorption_events

        avg_volume = candles['volume'].rolling(20).mean()

        for idx, candle in candles.iterrows():
            if pd.isna(avg_volume.loc[idx]):
                continue

            volume_ratio = candle['volume'] / avg_volume.loc[idx]
            price_change_pct = abs(candle['close'] - candle['open']) / candle['open'] * 100

            # High volume but small price change = absorption
            if volume_ratio >= volume_threshold_multiplier and price_change_pct <= price_change_threshold:
                # Determine if buying or selling absorption
                absorption_type = 'buy_absorption' if candle['close'] > candle['open'] else 'sell_absorption'

                absorption_events.append((idx, absorption_type))
                logger.debug(f"Absorption detected at {idx}: {absorption_type}")

        return absorption_events
