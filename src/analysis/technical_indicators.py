"""
Technical Indicators Calculator

Calculates common technical indicators:
- Moving Averages (SMA, EMA)
- RSI (Relative Strength Index)
- MACD (Moving Average Convergence Divergence)
- Bollinger Bands
- ATR (Average True Range)
- Stochastic Oscillator
- Volume indicators
"""

import pandas as pd
import numpy as np
from typing import Dict, Any, List, Optional, Tuple
from loguru import logger


class TechnicalIndicators:
    """
    Calculate technical indicators from OHLCV data

    All methods return pandas Series or DataFrame that can be easily
    added to existing dataframe or visualized.
    """

    @staticmethod
    def sma(data: pd.Series, period: int = 20) -> pd.Series:
        """
        Simple Moving Average

        Args:
            data: Price series (usually close)
            period: Lookback period

        Returns:
            SMA series
        """
        return data.rolling(window=period).mean()

    @staticmethod
    def ema(data: pd.Series, period: int = 20) -> pd.Series:
        """
        Exponential Moving Average

        Args:
            data: Price series (usually close)
            period: Lookback period

        Returns:
            EMA series
        """
        return data.ewm(span=period, adjust=False).mean()

    @staticmethod
    def rsi(data: pd.Series, period: int = 14) -> pd.Series:
        """
        Relative Strength Index

        Args:
            data: Price series (usually close)
            period: Lookback period (default: 14)

        Returns:
            RSI series (0-100)
        """
        delta = data.diff()

        gain = delta.where(delta > 0, 0)
        loss = -delta.where(delta < 0, 0)

        avg_gain = gain.rolling(window=period).mean()
        avg_loss = loss.rolling(window=period).mean()

        rs = avg_gain / avg_loss
        rsi = 100 - (100 / (1 + rs))

        return rsi

    @staticmethod
    def macd(
        data: pd.Series,
        fast: int = 12,
        slow: int = 26,
        signal: int = 9
    ) -> pd.DataFrame:
        """
        MACD (Moving Average Convergence Divergence)

        Args:
            data: Price series (usually close)
            fast: Fast EMA period (default: 12)
            slow: Slow EMA period (default: 26)
            signal: Signal line period (default: 9)

        Returns:
            DataFrame with macd, signal, and histogram columns
        """
        ema_fast = data.ewm(span=fast, adjust=False).mean()
        ema_slow = data.ewm(span=slow, adjust=False).mean()

        macd_line = ema_fast - ema_slow
        signal_line = macd_line.ewm(span=signal, adjust=False).mean()
        histogram = macd_line - signal_line

        return pd.DataFrame({
            'macd': macd_line,
            'signal': signal_line,
            'histogram': histogram
        })

    @staticmethod
    def bollinger_bands(
        data: pd.Series,
        period: int = 20,
        std_dev: float = 2.0
    ) -> pd.DataFrame:
        """
        Bollinger Bands

        Args:
            data: Price series (usually close)
            period: MA period (default: 20)
            std_dev: Standard deviation multiplier (default: 2.0)

        Returns:
            DataFrame with upper, middle, and lower bands
        """
        middle = data.rolling(window=period).mean()
        std = data.rolling(window=period).std()

        upper = middle + (std * std_dev)
        lower = middle - (std * std_dev)

        return pd.DataFrame({
            'upper': upper,
            'middle': middle,
            'lower': lower
        })

    @staticmethod
    def atr(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.Series:
        """
        Average True Range

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: Lookback period (default: 14)

        Returns:
            ATR series
        """
        high_low = high - low
        high_close = abs(high - close.shift())
        low_close = abs(low - close.shift())

        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)
        atr = true_range.rolling(window=period).mean()

        return atr

    @staticmethod
    def stochastic(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14,
        smooth_k: int = 3,
        smooth_d: int = 3
    ) -> pd.DataFrame:
        """
        Stochastic Oscillator

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: Lookback period (default: 14)
            smooth_k: %K smoothing (default: 3)
            smooth_d: %D smoothing (default: 3)

        Returns:
            DataFrame with %K and %D lines
        """
        lowest_low = low.rolling(window=period).min()
        highest_high = high.rolling(window=period).max()

        k = 100 * ((close - lowest_low) / (highest_high - lowest_low))
        k_smooth = k.rolling(window=smooth_k).mean()
        d = k_smooth.rolling(window=smooth_d).mean()

        return pd.DataFrame({
            'k': k_smooth,
            'd': d
        })

    @staticmethod
    def vwap(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        volume: pd.Series
    ) -> pd.Series:
        """
        Volume Weighted Average Price

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            volume: Volume

        Returns:
            VWAP series
        """
        typical_price = (high + low + close) / 3
        return (typical_price * volume).cumsum() / volume.cumsum()

    @staticmethod
    def obv(close: pd.Series, volume: pd.Series) -> pd.Series:
        """
        On-Balance Volume

        Args:
            close: Close prices
            volume: Volume

        Returns:
            OBV series
        """
        direction = np.where(close.diff() > 0, 1, -1)
        direction[0] = 0
        obv = (direction * volume).cumsum()

        return pd.Series(obv, index=close.index)

    @staticmethod
    def adx(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 14
    ) -> pd.DataFrame:
        """
        Average Directional Index (ADX)

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: Lookback period (default: 14)

        Returns:
            DataFrame with ADX, +DI, -DI
        """
        # Calculate True Range
        high_low = high - low
        high_close = abs(high - close.shift())
        low_close = abs(low - close.shift())
        true_range = pd.concat([high_low, high_close, low_close], axis=1).max(axis=1)

        # Calculate +DM and -DM
        high_diff = high.diff()
        low_diff = -low.diff()

        plus_dm = np.where((high_diff > low_diff) & (high_diff > 0), high_diff, 0)
        minus_dm = np.where((low_diff > high_diff) & (low_diff > 0), low_diff, 0)

        # Smooth TR, +DM, -DM
        tr_smooth = pd.Series(true_range).rolling(window=period).mean()
        plus_dm_smooth = pd.Series(plus_dm).rolling(window=period).mean()
        minus_dm_smooth = pd.Series(minus_dm).rolling(window=period).mean()

        # Calculate +DI and -DI
        plus_di = 100 * (plus_dm_smooth / tr_smooth)
        minus_di = 100 * (minus_dm_smooth / tr_smooth)

        # Calculate DX and ADX
        dx = 100 * abs(plus_di - minus_di) / (plus_di + minus_di)
        adx = dx.rolling(window=period).mean()

        return pd.DataFrame({
            'adx': adx,
            'plus_di': plus_di,
            'minus_di': minus_di
        })

    @staticmethod
    def supertrend(
        high: pd.Series,
        low: pd.Series,
        close: pd.Series,
        period: int = 10,
        multiplier: float = 3.0
    ) -> pd.DataFrame:
        """
        Supertrend Indicator

        Args:
            high: High prices
            low: Low prices
            close: Close prices
            period: ATR period (default: 10)
            multiplier: ATR multiplier (default: 3.0)

        Returns:
            DataFrame with supertrend line and direction
        """
        # Calculate ATR
        atr = TechnicalIndicators.atr(high, low, close, period)

        # Calculate basic bands
        hl_avg = (high + low) / 2
        upper_band = hl_avg + (multiplier * atr)
        lower_band = hl_avg - (multiplier * atr)

        # Initialize supertrend
        supertrend = pd.Series(index=close.index, dtype=float)
        direction = pd.Series(index=close.index, dtype=int)

        for i in range(period, len(close)):
            if i == period:
                supertrend.iloc[i] = upper_band.iloc[i] if close.iloc[i] <= upper_band.iloc[i] else lower_band.iloc[i]
                direction.iloc[i] = -1 if close.iloc[i] <= upper_band.iloc[i] else 1
            else:
                # Update upper band
                if upper_band.iloc[i] < upper_band.iloc[i-1] or close.iloc[i-1] > upper_band.iloc[i-1]:
                    upper_band.iloc[i] = upper_band.iloc[i]
                else:
                    upper_band.iloc[i] = upper_band.iloc[i-1]

                # Update lower band
                if lower_band.iloc[i] > lower_band.iloc[i-1] or close.iloc[i-1] < lower_band.iloc[i-1]:
                    lower_band.iloc[i] = lower_band.iloc[i]
                else:
                    lower_band.iloc[i] = lower_band.iloc[i-1]

                # Determine supertrend
                if supertrend.iloc[i-1] == upper_band.iloc[i-1] and close.iloc[i] <= upper_band.iloc[i]:
                    supertrend.iloc[i] = upper_band.iloc[i]
                    direction.iloc[i] = -1
                elif supertrend.iloc[i-1] == upper_band.iloc[i-1] and close.iloc[i] > upper_band.iloc[i]:
                    supertrend.iloc[i] = lower_band.iloc[i]
                    direction.iloc[i] = 1
                elif supertrend.iloc[i-1] == lower_band.iloc[i-1] and close.iloc[i] >= lower_band.iloc[i]:
                    supertrend.iloc[i] = lower_band.iloc[i]
                    direction.iloc[i] = 1
                elif supertrend.iloc[i-1] == lower_band.iloc[i-1] and close.iloc[i] < lower_band.iloc[i]:
                    supertrend.iloc[i] = upper_band.iloc[i]
                    direction.iloc[i] = -1

        return pd.DataFrame({
            'supertrend': supertrend,
            'direction': direction  # 1 = bullish, -1 = bearish
        })

    @staticmethod
    def calculate_all(
        df: pd.DataFrame,
        indicators: Optional[List[str]] = None
    ) -> pd.DataFrame:
        """
        Calculate all technical indicators

        Args:
            df: DataFrame with OHLCV columns (open, high, low, close, volume)
            indicators: List of indicators to calculate (None = all)

        Returns:
            DataFrame with original data plus indicators
        """
        result = df.copy()

        # Available indicators
        all_indicators = [
            'sma_20', 'sma_50', 'sma_200',
            'ema_9', 'ema_21', 'ema_50',
            'rsi', 'macd', 'bollinger', 'atr',
            'stochastic', 'vwap', 'obv', 'adx', 'supertrend'
        ]

        # Use specified indicators or all
        to_calculate = indicators if indicators else all_indicators

        try:
            # Moving Averages
            if 'sma_20' in to_calculate:
                result['sma_20'] = TechnicalIndicators.sma(df['close'], 20)
            if 'sma_50' in to_calculate:
                result['sma_50'] = TechnicalIndicators.sma(df['close'], 50)
            if 'sma_200' in to_calculate:
                result['sma_200'] = TechnicalIndicators.sma(df['close'], 200)

            if 'ema_9' in to_calculate:
                result['ema_9'] = TechnicalIndicators.ema(df['close'], 9)
            if 'ema_21' in to_calculate:
                result['ema_21'] = TechnicalIndicators.ema(df['close'], 21)
            if 'ema_50' in to_calculate:
                result['ema_50'] = TechnicalIndicators.ema(df['close'], 50)

            # RSI
            if 'rsi' in to_calculate:
                result['rsi'] = TechnicalIndicators.rsi(df['close'])

            # MACD
            if 'macd' in to_calculate:
                macd_df = TechnicalIndicators.macd(df['close'])
                result['macd'] = macd_df['macd']
                result['macd_signal'] = macd_df['signal']
                result['macd_histogram'] = macd_df['histogram']

            # Bollinger Bands
            if 'bollinger' in to_calculate:
                bb_df = TechnicalIndicators.bollinger_bands(df['close'])
                result['bb_upper'] = bb_df['upper']
                result['bb_middle'] = bb_df['middle']
                result['bb_lower'] = bb_df['lower']

            # ATR
            if 'atr' in to_calculate:
                result['atr'] = TechnicalIndicators.atr(
                    df['high'], df['low'], df['close']
                )

            # Stochastic
            if 'stochastic' in to_calculate:
                stoch_df = TechnicalIndicators.stochastic(
                    df['high'], df['low'], df['close']
                )
                result['stoch_k'] = stoch_df['k']
                result['stoch_d'] = stoch_df['d']

            # VWAP
            if 'vwap' in to_calculate:
                result['vwap'] = TechnicalIndicators.vwap(
                    df['high'], df['low'], df['close'], df['volume']
                )

            # OBV
            if 'obv' in to_calculate:
                result['obv'] = TechnicalIndicators.obv(df['close'], df['volume'])

            # ADX
            if 'adx' in to_calculate:
                adx_df = TechnicalIndicators.adx(
                    df['high'], df['low'], df['close']
                )
                result['adx'] = adx_df['adx']
                result['plus_di'] = adx_df['plus_di']
                result['minus_di'] = adx_df['minus_di']

            # Supertrend
            if 'supertrend' in to_calculate:
                st_df = TechnicalIndicators.supertrend(
                    df['high'], df['low'], df['close']
                )
                result['supertrend'] = st_df['supertrend']
                result['supertrend_direction'] = st_df['direction']

            logger.info(f"Calculated {len(to_calculate)} technical indicators")

        except Exception as e:
            logger.error(f"Error calculating indicators: {e}")

        return result


# Utility functions

def identify_trends(df: pd.DataFrame) -> Dict[str, str]:
    """
    Identify current trends based on indicators

    Args:
        df: DataFrame with calculated indicators

    Returns:
        Dict with trend analysis
    """
    latest = df.iloc[-1]

    trends = {}

    # SMA trend
    if 'sma_20' in df.columns and 'sma_50' in df.columns:
        if latest['close'] > latest['sma_20'] > latest['sma_50']:
            trends['sma_trend'] = 'strong_bullish'
        elif latest['close'] > latest['sma_20']:
            trends['sma_trend'] = 'bullish'
        elif latest['close'] < latest['sma_20'] < latest['sma_50']:
            trends['sma_trend'] = 'strong_bearish'
        else:
            trends['sma_trend'] = 'bearish'

    # RSI
    if 'rsi' in df.columns:
        rsi = latest['rsi']
        if rsi > 70:
            trends['rsi_signal'] = 'overbought'
        elif rsi < 30:
            trends['rsi_signal'] = 'oversold'
        else:
            trends['rsi_signal'] = 'neutral'

    # MACD
    if 'macd' in df.columns and 'macd_signal' in df.columns:
        if latest['macd'] > latest['macd_signal']:
            trends['macd_signal'] = 'bullish'
        else:
            trends['macd_signal'] = 'bearish'

    # Supertrend
    if 'supertrend_direction' in df.columns:
        if latest['supertrend_direction'] == 1:
            trends['supertrend'] = 'bullish'
        else:
            trends['supertrend'] = 'bearish'

    return trends


def get_support_resistance(df: pd.DataFrame, lookback: int = 20) -> Dict[str, List[float]]:
    """
    Identify support and resistance levels

    Args:
        df: DataFrame with OHLCV data
        lookback: Lookback period for pivot points

    Returns:
        Dict with support and resistance levels
    """
    recent = df.tail(lookback * 2)

    # Find pivot highs and lows
    resistance_levels = []
    support_levels = []

    for i in range(lookback, len(recent) - lookback):
        # Pivot high
        if all(recent['high'].iloc[i] > recent['high'].iloc[i-j] for j in range(1, lookback+1)) and \
           all(recent['high'].iloc[i] > recent['high'].iloc[i+j] for j in range(1, lookback+1)):
            resistance_levels.append(recent['high'].iloc[i])

        # Pivot low
        if all(recent['low'].iloc[i] < recent['low'].iloc[i-j] for j in range(1, lookback+1)) and \
           all(recent['low'].iloc[i] < recent['low'].iloc[i+j] for j in range(1, lookback+1)):
            support_levels.append(recent['low'].iloc[i])

    return {
        'resistance': sorted(resistance_levels, reverse=True)[:3],  # Top 3
        'support': sorted(support_levels)[-3:]  # Bottom 3
    }
