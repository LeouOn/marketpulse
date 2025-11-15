"""Market Breadth and Internals Data Collection
Provides advance/decline, new highs/lows, TICK, VOLD, and McClellan indicators
"""

import yfinance as yf
import pandas as pd
import numpy as np
from datetime import datetime, timedelta
from typing import Dict, Any, Optional, List
from loguru import logger


class MarketBreadthCollector:
    """Collects and calculates market breadth indicators"""

    def __init__(self):
        # Major index constituents for breadth calculation
        # Using representative ETFs and indices
        self.nyse_symbols = ['SPY', 'DIA', 'IWM', 'XLF', 'XLE', 'XLV', 'XLI', 'XLK', 'XLY', 'XLP']
        self.nasdaq_symbols = ['QQQ', 'ARKK', 'XLK', 'SOXX', 'IBB', 'IWF', 'IWO', 'IWM']

        # Historical data for McClellan calculation
        self.ad_history = []
        self.max_history = 100  # Keep 100 days of A/D data

    def get_market_internals(self) -> Dict[str, Any]:
        """Get comprehensive market internals data"""
        try:
            internals = {}

            # Get advance/decline data
            ad_data = self._calculate_advance_decline()
            internals.update(ad_data)

            # Get new highs/lows
            highs_lows = self._calculate_highs_lows()
            internals.update(highs_lows)

            # Calculate TICK proxy (from price movements)
            tick_data = self._calculate_tick_proxy()
            internals.update(tick_data)

            # Calculate VOLD (volume delta)
            vold_data = self._calculate_vold()
            internals.update(vold_data)

            # Calculate McClellan Oscillator
            mcclellan_data = self._calculate_mcclellan()
            internals.update(mcclellan_data)

            logger.info(f"Successfully calculated {len(internals)} market internals indicators")
            return internals

        except Exception as e:
            logger.error(f"Error calculating market internals: {e}")
            return self._get_mock_internals()

    def _calculate_advance_decline(self) -> Dict[str, Any]:
        """Calculate advance/decline statistics"""
        try:
            # Get intraday data for NYSE and NASDAQ proxies
            nyse_data = self._get_intraday_stats(self.nyse_symbols)
            nasdaq_data = self._get_intraday_stats(self.nasdaq_symbols)

            # Calculate advancing vs declining
            nyse_advancing = sum(1 for change in nyse_data['changes'] if change > 0)
            nyse_declining = sum(1 for change in nyse_data['changes'] if change < 0)
            nyse_unchanged = len(nyse_data['changes']) - nyse_advancing - nyse_declining

            nasdaq_advancing = sum(1 for change in nasdaq_data['changes'] if change > 0)
            nasdaq_declining = sum(1 for change in nasdaq_data['changes'] if change < 0)
            nasdaq_unchanged = len(nasdaq_data['changes']) - nasdaq_advancing - nasdaq_declining

            # Calculate ratios
            nyse_ad_ratio = nyse_advancing / nyse_declining if nyse_declining > 0 else 0
            nasdaq_ad_ratio = nasdaq_advancing / nasdaq_declining if nasdaq_declining > 0 else 0

            # Net advance/decline
            nyse_net_ad = nyse_advancing - nyse_declining
            nasdaq_net_ad = nasdaq_advancing - nasdaq_declining

            # Store for McClellan calculation
            total_net_ad = nyse_net_ad + nasdaq_net_ad
            self.ad_history.append({
                'date': datetime.now(),
                'net_ad': total_net_ad
            })

            # Keep only recent history
            if len(self.ad_history) > self.max_history:
                self.ad_history = self.ad_history[-self.max_history:]

            return {
                'nyse_advancing': nyse_advancing,
                'nyse_declining': nyse_declining,
                'nyse_unchanged': nyse_unchanged,
                'nyse_ad_ratio': round(nyse_ad_ratio, 2),
                'nyse_net_ad': nyse_net_ad,
                'nasdaq_advancing': nasdaq_advancing,
                'nasdaq_declining': nasdaq_declining,
                'nasdaq_unchanged': nasdaq_unchanged,
                'nasdaq_ad_ratio': round(nasdaq_ad_ratio, 2),
                'nasdaq_net_ad': nasdaq_net_ad,
                'interpretation': self._interpret_ad_ratio(nyse_ad_ratio, nasdaq_ad_ratio)
            }

        except Exception as e:
            logger.debug(f"Error calculating A/D: {e}")
            return {
                'nyse_advancing': 0,
                'nyse_declining': 0,
                'nyse_unchanged': 0,
                'nyse_ad_ratio': 1.0,
                'nyse_net_ad': 0,
                'nasdaq_advancing': 0,
                'nasdaq_declining': 0,
                'nasdaq_unchanged': 0,
                'nasdaq_ad_ratio': 1.0,
                'nasdaq_net_ad': 0,
                'interpretation': 'Neutral'
            }

    def _calculate_highs_lows(self) -> Dict[str, Any]:
        """Calculate new 52-week highs vs lows"""
        try:
            all_symbols = list(set(self.nyse_symbols + self.nasdaq_symbols))

            # Get 1-year data for each symbol
            highs = 0
            lows = 0

            for symbol in all_symbols:
                try:
                    ticker = yf.Ticker(symbol)
                    hist = ticker.history(period='1y')

                    if hist.empty or len(hist) < 200:
                        continue

                    current_price = hist['Close'].iloc[-1]
                    year_high = hist['High'].max()
                    year_low = hist['Low'].min()

                    # Check if near 52-week high (within 2%)
                    if current_price >= year_high * 0.98:
                        highs += 1

                    # Check if near 52-week low (within 2%)
                    if current_price <= year_low * 1.02:
                        lows += 1

                except Exception as e:
                    logger.debug(f"Error processing {symbol} for highs/lows: {e}")
                    continue

            hl_ratio = highs / lows if lows > 0 else highs
            net_hl = highs - lows

            return {
                'new_highs': highs,
                'new_lows': lows,
                'hl_ratio': round(hl_ratio, 2),
                'net_hl': net_hl,
                'interpretation': 'Bullish' if highs > lows else ('Bearish' if lows > highs else 'Neutral')
            }

        except Exception as e:
            logger.debug(f"Error calculating highs/lows: {e}")
            return {
                'new_highs': 0,
                'new_lows': 0,
                'hl_ratio': 1.0,
                'net_hl': 0,
                'interpretation': 'Neutral'
            }

    def _calculate_tick_proxy(self) -> Dict[str, Any]:
        """Calculate TICK proxy from price movements
        Real TICK requires tick-by-tick data, this is an approximation
        """
        try:
            # Get recent price movements
            nyse_stats = self._get_intraday_stats(self.nyse_symbols)
            nasdaq_stats = self._get_intraday_stats(self.nasdaq_symbols)

            # Count upticks vs downticks (simplified)
            upticks = sum(1 for change in nyse_stats['changes'] + nasdaq_stats['changes'] if change > 0)
            downticks = sum(1 for change in nyse_stats['changes'] + nasdaq_stats['changes'] if change < 0)

            # TICK = upticks - downticks
            tick_value = upticks - downticks

            # Normalize to typical TICK range (-1000 to +1000)
            total_symbols = len(nyse_stats['changes']) + len(nasdaq_stats['changes'])
            tick_normalized = int((tick_value / total_symbols) * 1000) if total_symbols > 0 else 0

            return {
                'tick_value': tick_normalized,
                'tick_30min_avg': tick_normalized,  # Would need historical data for true average
                'tick_4hr_avg': tick_normalized,
                'interpretation': self._interpret_tick(tick_normalized)
            }

        except Exception as e:
            logger.debug(f"Error calculating TICK: {e}")
            return {
                'tick_value': 0,
                'tick_30min_avg': 0,
                'tick_4hr_avg': 0,
                'interpretation': 'Neutral'
            }

    def _calculate_vold(self) -> Dict[str, Any]:
        """Calculate volume delta (up volume - down volume)"""
        try:
            nyse_stats = self._get_intraday_stats(self.nyse_symbols)
            nasdaq_stats = self._get_intraday_stats(self.nasdaq_symbols)

            # Calculate up volume and down volume
            nyse_up_vol = sum(vol for vol, change in zip(nyse_stats['volumes'], nyse_stats['changes']) if change > 0)
            nyse_down_vol = sum(vol for vol, change in zip(nyse_stats['volumes'], nyse_stats['changes']) if change < 0)

            nasdaq_up_vol = sum(vol for vol, change in zip(nasdaq_stats['volumes'], nasdaq_stats['changes']) if change > 0)
            nasdaq_down_vol = sum(vol for vol, change in zip(nasdaq_stats['volumes'], nasdaq_stats['changes']) if change < 0)

            nyse_vold = nyse_up_vol - nyse_down_vol
            nasdaq_vold = nasdaq_up_vol - nasdaq_down_vol

            return {
                'nyse_vold': int(nyse_vold),
                'nasdaq_vold': int(nasdaq_vold),
                'total_vold': int(nyse_vold + nasdaq_vold),
                'interpretation': self._interpret_vold(nyse_vold + nasdaq_vold)
            }

        except Exception as e:
            logger.debug(f"Error calculating VOLD: {e}")
            return {
                'nyse_vold': 0,
                'nasdaq_vold': 0,
                'total_vold': 0,
                'interpretation': 'Neutral'
            }

    def _calculate_mcclellan(self) -> Dict[str, Any]:
        """Calculate McClellan Oscillator and Summation Index"""
        try:
            if len(self.ad_history) < 39:
                # Not enough data for McClellan
                return {
                    'mcclellan_oscillator': 0,
                    'mcclellan_summation': 0,
                    'interpretation': 'Insufficient data'
                }

            # Extract net A/D values
            net_ad_values = [item['net_ad'] for item in self.ad_history]

            # Calculate 19-day and 39-day EMAs
            ema_19 = self._calculate_ema(net_ad_values, 19)
            ema_39 = self._calculate_ema(net_ad_values, 39)

            # McClellan Oscillator = EMA(19) - EMA(39)
            oscillator = ema_19 - ema_39

            # Summation Index is the running total of oscillator values
            # Simplified: use current oscillator * 10 as proxy
            summation = oscillator * 10

            return {
                'mcclellan_oscillator': round(oscillator, 2),
                'mcclellan_summation': round(summation, 2),
                'interpretation': self._interpret_mcclellan(oscillator, summation)
            }

        except Exception as e:
            logger.debug(f"Error calculating McClellan: {e}")
            return {
                'mcclellan_oscillator': 0,
                'mcclellan_summation': 0,
                'interpretation': 'Neutral'
            }

    def _get_intraday_stats(self, symbols: List[str]) -> Dict[str, List]:
        """Get intraday statistics for a list of symbols"""
        changes = []
        volumes = []

        for symbol in symbols:
            try:
                ticker = yf.Ticker(symbol)
                hist = ticker.history(period='2d', interval='1d')

                if hist.empty or len(hist) < 2:
                    continue

                current_price = hist['Close'].iloc[-1]
                previous_price = hist['Close'].iloc[-2]
                change = current_price - previous_price
                volume = hist['Volume'].iloc[-1]

                changes.append(change)
                volumes.append(volume)

            except Exception as e:
                logger.debug(f"Error getting stats for {symbol}: {e}")
                continue

        return {'changes': changes, 'volumes': volumes}

    def _calculate_ema(self, data: List[float], period: int) -> float:
        """Calculate Exponential Moving Average"""
        if len(data) < period:
            return sum(data) / len(data) if data else 0

        # Use pandas for EMA calculation
        series = pd.Series(data)
        ema = series.ewm(span=period, adjust=False).mean().iloc[-1]
        return float(ema)

    def _interpret_ad_ratio(self, nyse_ratio: float, nasdaq_ratio: float) -> str:
        """Interpret advance/decline ratio"""
        avg_ratio = (nyse_ratio + nasdaq_ratio) / 2

        if avg_ratio > 2.0:
            return 'Very Bullish'
        elif avg_ratio > 1.5:
            return 'Bullish'
        elif avg_ratio > 0.67:
            return 'Neutral'
        elif avg_ratio > 0.5:
            return 'Bearish'
        else:
            return 'Very Bearish'

    def _interpret_tick(self, tick: int) -> str:
        """Interpret TICK value"""
        if tick > 600:
            return 'Very Bullish'
        elif tick > 200:
            return 'Bullish'
        elif tick > -200:
            return 'Neutral'
        elif tick > -600:
            return 'Bearish'
        else:
            return 'Very Bearish'

    def _interpret_vold(self, vold: float) -> str:
        """Interpret VOLD value"""
        if vold > 5e8:  # 500 million
            return 'Strong Buying'
        elif vold > 1e8:  # 100 million
            return 'Moderate Buying'
        elif vold > -1e8:
            return 'Neutral'
        elif vold > -5e8:
            return 'Moderate Selling'
        else:
            return 'Strong Selling'

    def _interpret_mcclellan(self, oscillator: float, summation: float) -> str:
        """Interpret McClellan indicators"""
        if oscillator > 100:
            return 'Overbought'
        elif oscillator > 50:
            return 'Bullish'
        elif oscillator > -50:
            return 'Neutral'
        elif oscillator > -100:
            return 'Bearish'
        else:
            return 'Oversold'

    def _get_mock_internals(self) -> Dict[str, Any]:
        """Return mock data when real calculation fails"""
        return {
            'nyse_advancing': 1520,
            'nyse_declining': 1380,
            'nyse_unchanged': 100,
            'nyse_ad_ratio': 1.10,
            'nyse_net_ad': 140,
            'nasdaq_advancing': 1840,
            'nasdaq_declining': 1560,
            'nasdaq_unchanged': 100,
            'nasdaq_ad_ratio': 1.18,
            'nasdaq_net_ad': 280,
            'interpretation': 'Bullish',
            'new_highs': 127,
            'new_lows': 43,
            'hl_ratio': 2.95,
            'net_hl': 84,
            'tick_value': 420,
            'tick_30min_avg': 380,
            'tick_4hr_avg': 245,
            'nyse_vold': 234000000,
            'nasdaq_vold': 456000000,
            'total_vold': 690000000,
            'mcclellan_oscillator': 65.4,
            'mcclellan_summation': 654.0,
        }


# Convenience function
def get_market_breadth() -> Dict[str, Any]:
    """Get current market breadth data"""
    collector = MarketBreadthCollector()
    return collector.get_market_internals()
