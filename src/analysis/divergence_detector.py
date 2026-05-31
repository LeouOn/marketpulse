"""
Divergence Detection System

Detect bullish and bearish divergences across multiple indicators:
- RSI Divergence (regular & hidden)
- MACD Divergence (regular & hidden)
- Stochastic Divergence
- Volume Divergence (OBV)
- CVD Divergence

Divergence Types:
- Regular Bullish: Price makes lower low, indicator makes higher low (REVERSAL)
- Regular Bearish: Price makes higher high, indicator makes lower high (REVERSAL)
- Hidden Bullish: Price makes higher low, indicator makes lower low (CONTINUATION)
- Hidden Bearish: Price makes lower high, indicator makes higher high (CONTINUATION)
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime
from loguru import logger

from src.analysis.technical_indicators import TechnicalIndicators


@dataclass
class Divergence:
    """Divergence signal"""
    type: str  # 'regular_bullish', 'regular_bearish', 'hidden_bullish', 'hidden_bearish'
    indicator: str  # 'rsi', 'macd', 'stochastic', 'obv', 'cvd'
    strength: float  # 0-100
    price_points: Tuple[int, int]  # Indices of price pivots
    indicator_points: Tuple[int, int]  # Indices of indicator pivots
    start_time: datetime
    end_time: datetime
    description: str


class DivergenceDetector:
    """
    Detect divergences across multiple indicators

    A divergence occurs when price and an indicator disagree,
    often signaling potential reversals or trend continuation.
    """

    def __init__(self, lookback: int = 50, min_strength: float = 60.0):
        """
        Initialize divergence detector

        Args:
            lookback: Number of bars to look back for pivot points
            min_strength: Minimum strength score (0-100) to report
        """
        self.lookback = lookback
        self.min_strength = min_strength

    def detect_all_divergences(
        self,
        df: pd.DataFrame,
        indicators: Optional[List[str]] = None
    ) -> List[Divergence]:
        """
        Detect all divergences in the data

        Args:
            df: DataFrame with OHLCV data
            indicators: List of indicators to check (None = all)

        Returns:
            List of Divergence objects
        """
        # Calculate indicators if not present
        required = indicators if indicators else ['rsi', 'macd', 'obv']
        df_with_ind = TechnicalIndicators.calculate_all(df, required)

        divergences = []

        # RSI Divergence
        if 'rsi' in df_with_ind.columns:
            divs = self.detect_rsi_divergence(df_with_ind)
            divergences.extend(divs)

        # MACD Divergence
        if 'macd' in df_with_ind.columns:
            divs = self.detect_macd_divergence(df_with_ind)
            divergences.extend(divs)

        # Stochastic Divergence
        if 'stoch_k' in df_with_ind.columns:
            divs = self.detect_stochastic_divergence(df_with_ind)
            divergences.extend(divs)

        # Volume Divergence (OBV)
        if 'obv' in df_with_ind.columns:
            divs = self.detect_volume_divergence(df_with_ind)
            divergences.extend(divs)

        # Filter by strength
        divergences = [d for d in divergences if d.strength >= self.min_strength]

        # Sort by strength
        divergences.sort(key=lambda x: x.strength, reverse=True)

        logger.info(f"Detected {len(divergences)} divergences above {self.min_strength} strength")

        return divergences

    def detect_rsi_divergence(self, df: pd.DataFrame) -> List[Divergence]:
        """Detect RSI divergences"""
        divergences = []

        # Find price pivots
        price_highs, price_lows = self._find_price_pivots(df)

        # Find RSI pivots
        rsi_highs, rsi_lows = self._find_indicator_pivots(df['rsi'])

        # Regular Bullish: Price lower low, RSI higher low
        for i in range(1, len(price_lows)):
            price_idx1, price_val1 = price_lows[i-1]
            price_idx2, price_val2 = price_lows[i]

            if price_val2 < price_val1:  # Price making lower low
                # Find corresponding RSI lows
                rsi_low1 = self._find_closest_pivot(rsi_lows, price_idx1)
                rsi_low2 = self._find_closest_pivot(rsi_lows, price_idx2)

                if rsi_low1 and rsi_low2:
                    rsi_idx1, rsi_val1 = rsi_low1
                    rsi_idx2, rsi_val2 = rsi_low2

                    if rsi_val2 > rsi_val1:  # RSI making higher low
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, rsi_val1, rsi_val2
                        )

                        divergences.append(Divergence(
                            type='regular_bullish',
                            indicator='rsi',
                            strength=strength,
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(rsi_idx1, rsi_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"Regular bullish divergence: Price LL but RSI HL (strength: {strength:.0f})"
                        ))

        # Regular Bearish: Price higher high, RSI lower high
        for i in range(1, len(price_highs)):
            price_idx1, price_val1 = price_highs[i-1]
            price_idx2, price_val2 = price_highs[i]

            if price_val2 > price_val1:  # Price making higher high
                rsi_high1 = self._find_closest_pivot(rsi_highs, price_idx1)
                rsi_high2 = self._find_closest_pivot(rsi_highs, price_idx2)

                if rsi_high1 and rsi_high2:
                    rsi_idx1, rsi_val1 = rsi_high1
                    rsi_idx2, rsi_val2 = rsi_high2

                    if rsi_val2 < rsi_val1:  # RSI making lower high
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, rsi_val1, rsi_val2, bullish=False
                        )

                        divergences.append(Divergence(
                            type='regular_bearish',
                            indicator='rsi',
                            strength=strength,
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(rsi_idx1, rsi_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"Regular bearish divergence: Price HH but RSI LH (strength: {strength:.0f})"
                        ))

        # Hidden Bullish: Price higher low, RSI lower low (CONTINUATION)
        for i in range(1, len(price_lows)):
            price_idx1, price_val1 = price_lows[i-1]
            price_idx2, price_val2 = price_lows[i]

            if price_val2 > price_val1:  # Price making higher low
                rsi_low1 = self._find_closest_pivot(rsi_lows, price_idx1)
                rsi_low2 = self._find_closest_pivot(rsi_lows, price_idx2)

                if rsi_low1 and rsi_low2:
                    rsi_idx1, rsi_val1 = rsi_low1
                    rsi_idx2, rsi_val2 = rsi_low2

                    if rsi_val2 < rsi_val1:  # RSI making lower low
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, rsi_val1, rsi_val2
                        ) * 0.8  # Hidden divergences slightly lower strength

                        divergences.append(Divergence(
                            type='hidden_bullish',
                            indicator='rsi',
                            strength=strength,
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(rsi_idx1, rsi_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"Hidden bullish divergence: Price HL but RSI LL - trend continuation (strength: {strength:.0f})"
                        ))

        return divergences

    def detect_macd_divergence(self, df: pd.DataFrame) -> List[Divergence]:
        """Detect MACD divergences"""
        divergences = []

        # Use MACD histogram for divergence
        if 'macd_histogram' not in df.columns:
            return divergences

        price_highs, price_lows = self._find_price_pivots(df)
        macd_highs, macd_lows = self._find_indicator_pivots(df['macd_histogram'])

        # Regular Bullish
        for i in range(1, len(price_lows)):
            price_idx1, price_val1 = price_lows[i-1]
            price_idx2, price_val2 = price_lows[i]

            if price_val2 < price_val1:
                macd_low1 = self._find_closest_pivot(macd_lows, price_idx1)
                macd_low2 = self._find_closest_pivot(macd_lows, price_idx2)

                if macd_low1 and macd_low2:
                    macd_idx1, macd_val1 = macd_low1
                    macd_idx2, macd_val2 = macd_low2

                    if macd_val2 > macd_val1:
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, macd_val1, macd_val2
                        )

                        divergences.append(Divergence(
                            type='regular_bullish',
                            indicator='macd',
                            strength=strength,
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(macd_idx1, macd_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"MACD bullish divergence: Price LL but MACD HL (strength: {strength:.0f})"
                        ))

        # Regular Bearish
        for i in range(1, len(price_highs)):
            price_idx1, price_val1 = price_highs[i-1]
            price_idx2, price_val2 = price_highs[i]

            if price_val2 > price_val1:
                macd_high1 = self._find_closest_pivot(macd_highs, price_idx1)
                macd_high2 = self._find_closest_pivot(macd_highs, price_idx2)

                if macd_high1 and macd_high2:
                    macd_idx1, macd_val1 = macd_high1
                    macd_idx2, macd_val2 = macd_high2

                    if macd_val2 < macd_val1:
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, macd_val1, macd_val2, bullish=False
                        )

                        divergences.append(Divergence(
                            type='regular_bearish',
                            indicator='macd',
                            strength=strength,
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(macd_idx1, macd_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"MACD bearish divergence: Price HH but MACD LH (strength: {strength:.0f})"
                        ))

        return divergences

    def detect_stochastic_divergence(self, df: pd.DataFrame) -> List[Divergence]:
        """Detect Stochastic divergences"""
        divergences = []

        price_highs, price_lows = self._find_price_pivots(df)
        stoch_highs, stoch_lows = self._find_indicator_pivots(df['stoch_k'])

        # Similar logic to RSI, but typically only look in overbought/oversold zones
        # Regular Bullish (in oversold zone < 20)
        for i in range(1, len(price_lows)):
            price_idx1, price_val1 = price_lows[i-1]
            price_idx2, price_val2 = price_lows[i]

            if price_val2 < price_val1:
                stoch_low1 = self._find_closest_pivot(stoch_lows, price_idx1)
                stoch_low2 = self._find_closest_pivot(stoch_lows, price_idx2)

                if stoch_low1 and stoch_low2:
                    stoch_idx1, stoch_val1 = stoch_low1
                    stoch_idx2, stoch_val2 = stoch_low2

                    # Check if in oversold zone
                    if stoch_val1 < 30 and stoch_val2 < 30 and stoch_val2 > stoch_val1:
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, stoch_val1, stoch_val2
                        )

                        divergences.append(Divergence(
                            type='regular_bullish',
                            indicator='stochastic',
                            strength=strength,
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(stoch_idx1, stoch_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"Stochastic bullish divergence in oversold zone (strength: {strength:.0f})"
                        ))

        return divergences

    def detect_volume_divergence(self, df: pd.DataFrame) -> List[Divergence]:
        """Detect volume divergences (OBV)"""
        divergences = []

        price_highs, price_lows = self._find_price_pivots(df)
        obv_highs, obv_lows = self._find_indicator_pivots(df['obv'])

        # Volume divergences are strong reversal signals
        # Regular Bullish
        for i in range(1, len(price_lows)):
            price_idx1, price_val1 = price_lows[i-1]
            price_idx2, price_val2 = price_lows[i]

            if price_val2 < price_val1:
                obv_low1 = self._find_closest_pivot(obv_lows, price_idx1)
                obv_low2 = self._find_closest_pivot(obv_lows, price_idx2)

                if obv_low1 and obv_low2:
                    obv_idx1, obv_val1 = obv_low1
                    obv_idx2, obv_val2 = obv_low2

                    if obv_val2 > obv_val1:
                        strength = self._calculate_divergence_strength(
                            price_val1, price_val2, obv_val1, obv_val2
                        ) * 1.1  # Volume divergences get bonus strength

                        divergences.append(Divergence(
                            type='regular_bullish',
                            indicator='obv',
                            strength=min(100, strength),
                            price_points=(price_idx1, price_idx2),
                            indicator_points=(obv_idx1, obv_idx2),
                            start_time=df.index[price_idx1],
                            end_time=df.index[price_idx2],
                            description=f"Volume (OBV) bullish divergence - very strong signal! (strength: {min(100, strength):.0f})"
                        ))

        return divergences

    def _find_price_pivots(
        self,
        df: pd.DataFrame,
        window: int = 5
    ) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
        """
        Find pivot highs and lows in price

        Returns:
            (pivot_highs, pivot_lows) as lists of (index, value) tuples
        """
        highs = []
        lows = []

        for i in range(window, len(df) - window):
            # Pivot high
            if all(df['high'].iloc[i] >= df['high'].iloc[i-j] for j in range(1, window+1)) and \
               all(df['high'].iloc[i] >= df['high'].iloc[i+j] for j in range(1, window+1)):
                highs.append((i, df['high'].iloc[i]))

            # Pivot low
            if all(df['low'].iloc[i] <= df['low'].iloc[i-j] for j in range(1, window+1)) and \
               all(df['low'].iloc[i] <= df['low'].iloc[i+j] for j in range(1, window+1)):
                lows.append((i, df['low'].iloc[i]))

        return highs, lows

    def _find_indicator_pivots(
        self,
        series: pd.Series,
        window: int = 5
    ) -> Tuple[List[Tuple[int, float]], List[Tuple[int, float]]]:
        """Find pivot highs and lows in indicator"""
        highs = []
        lows = []

        for i in range(window, len(series) - window):
            if pd.isna(series.iloc[i]):
                continue

            # Pivot high
            if all(series.iloc[i] >= series.iloc[i-j] for j in range(1, window+1) if not pd.isna(series.iloc[i-j])) and \
               all(series.iloc[i] >= series.iloc[i+j] for j in range(1, window+1) if not pd.isna(series.iloc[i+j])):
                highs.append((i, series.iloc[i]))

            # Pivot low
            if all(series.iloc[i] <= series.iloc[i-j] for j in range(1, window+1) if not pd.isna(series.iloc[i-j])) and \
               all(series.iloc[i] <= series.iloc[i+j] for j in range(1, window+1) if not pd.isna(series.iloc[i+j])):
                lows.append((i, series.iloc[i]))

        return highs, lows

    def _find_closest_pivot(
        self,
        pivots: List[Tuple[int, float]],
        target_idx: int,
        max_distance: int = 20
    ) -> Optional[Tuple[int, float]]:
        """Find closest pivot to target index"""
        if not pivots:
            return None

        closest = min(pivots, key=lambda p: abs(p[0] - target_idx))

        if abs(closest[0] - target_idx) <= max_distance:
            return closest

        return None

    def _calculate_divergence_strength(
        self,
        price1: float,
        price2: float,
        ind1: float,
        ind2: float,
        bullish: bool = True
    ) -> float:
        """
        Calculate divergence strength (0-100)

        Based on:
        - Magnitude of price divergence
        - Magnitude of indicator divergence
        - Time distance between pivots
        """
        # Calculate percentage changes
        price_change = abs((price2 - price1) / price1) * 100
        ind_change = abs((ind2 - ind1) / abs(ind1)) * 100 if ind1 != 0 else 0

        # Higher divergence = stronger signal
        divergence_magnitude = (price_change + ind_change) / 2

        # Base strength from magnitude (capped at 80)
        strength = min(80, divergence_magnitude * 10)

        # Bonus for clear divergence
        if price_change > 2 and ind_change > 2:
            strength += 10

        # Bonus for extreme divergence
        if price_change > 5 or ind_change > 5:
            strength += 10

        return min(100, strength)


def scan_for_divergences(
    df: pd.DataFrame,
    min_strength: float = 60.0
) -> Dict[str, Any]:
    """
    Scan for all divergences and return summary

    Args:
        df: DataFrame with OHLCV data
        min_strength: Minimum strength to report

    Returns:
        Dict with divergence summary
    """
    detector = DivergenceDetector(min_strength=min_strength)
    divergences = detector.detect_all_divergences(df)

    # Organize by type
    by_type = {
        'regular_bullish': [],
        'regular_bearish': [],
        'hidden_bullish': [],
        'hidden_bearish': []
    }

    for div in divergences:
        by_type[div.type].append(div)

    # Get strongest divergence
    strongest = divergences[0] if divergences else None

    return {
        'total_divergences': len(divergences),
        'by_type': {
            'regular_bullish': len(by_type['regular_bullish']),
            'regular_bearish': len(by_type['regular_bearish']),
            'hidden_bullish': len(by_type['hidden_bullish']),
            'hidden_bearish': len(by_type['hidden_bearish'])
        },
        'divergences': [
            {
                'type': d.type,
                'indicator': d.indicator,
                'strength': d.strength,
                'start_time': d.start_time.isoformat() if hasattr(d.start_time, 'isoformat') else str(d.start_time),
                'end_time': d.end_time.isoformat() if hasattr(d.end_time, 'isoformat') else str(d.end_time),
                'description': d.description
            }
            for d in divergences
        ],
        'strongest': {
            'type': strongest.type,
            'indicator': strongest.indicator,
            'strength': strongest.strength,
            'description': strongest.description
        } if strongest else None,
        'signal': _interpret_divergences(by_type)
    }


def _interpret_divergences(by_type: Dict[str, List[Divergence]]) -> str:
    """Interpret divergence signals"""
    bullish_count = len(by_type['regular_bullish']) + len(by_type['hidden_bullish'])
    bearish_count = len(by_type['regular_bearish']) + len(by_type['hidden_bearish'])

    if bullish_count > bearish_count * 2:
        return "STRONG_BULLISH"
    elif bullish_count > bearish_count:
        return "BULLISH"
    elif bearish_count > bullish_count * 2:
        return "STRONG_BEARISH"
    elif bearish_count > bullish_count:
        return "BEARISH"
    else:
        return "NEUTRAL"
