"""Modern Alpaca API Client for MarketPulse
Uses the new Alpaca-py SDK for real-time market data
"""

import asyncio
from datetime import datetime, timedelta
from typing import List, Dict, Optional, Any
import pandas as pd
from loguru import logger

try:
    from alpaca.data.historical import StockHistoricalDataClient
    from alpaca.data.requests import StockBarsRequest
    from alpaca.data.timeframe import TimeFrame
    from alpaca.data.live import StockDataStream
except ImportError as e:
    logger.error(f"Please install alpaca-py: pip install alpaca-py. Error: {e}")
    raise

from ..core.config import Settings


class ModernAlpacaClient:
    """Modern Alpaca Data API client using alpaca-py SDK"""

    def __init__(self, settings: Settings):
        self.settings = settings
        self.api_key = settings.api_keys.alpaca.key_id
        self.secret_key = settings.api_keys.alpaca.secret_key

        # Initialize the historical data client
        # For historical data, keys are optional for free data
        try:
            self.historical_client = StockHistoricalDataClient(
                api_key=self.api_key,
                secret_key=self.secret_key
            )
        except Exception as e:
            logger.warning(f"Failed to initialize client with keys, trying without: {e}")
            self.historical_client = StockHistoricalDataClient()

        # Important symbols for market internals
        self.key_symbols = [
            'SPY',    # S&P 500 ETF
            'QQQ',    # NASDAQ ETF
            'IWM',    # Russell 2000 ETF
            'DIA',    # Dow Jones ETF
            'AAPL',   # Large cap tech
            'TSLA',   # Growth stock
            'NVDA',   # AI/semiconductor
            'MSFT',   # Tech giant
            'GOOGL',  # Tech conglomerate
            'AMZN'    # E-commerce leader
        ]

        # ETF symbols for macro indicators
        self.macro_symbols = {
            'DXY': 'UUP',   # US Dollar Index ETF
            'GC': 'GLD',    # Gold ETF
            'CL': 'USO',    # Oil ETF
            'TNX': 'TNX'    # 10-Year Treasury Note (CBOE)
        }

    async def get_latest_bar(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get the most recent bar data for a symbol"""
        try:
            # Get data from the last 2 days to ensure we have recent data
            end_time = datetime.now()
            start_time = end_time - timedelta(days=2)

            request_params = StockBarsRequest(
                symbol_or_symbols=[symbol],
                timeframe=TimeFrame.Minute,
                start=start_time,
                end=end_time
            )

            # Get the bars
            bars = self.historical_client.get_stock_bars(request_params)

            if bars.data and symbol in bars.data:
                # Get the most recent bar
                symbol_bars = bars.data[symbol]
                if len(symbol_bars) > 0:
                    latest_bar = symbol_bars[-1]
                    return {
                        'symbol': symbol,
                        'timestamp': latest_bar.timestamp,
                        'open': latest_bar.open,
                        'high': latest_bar.high,
                        'low': latest_bar.low,
                        'close': latest_bar.close,
                        'volume': latest_bar.volume,
                        'trade_count': getattr(latest_bar, 'trade_count', 0),
                        'vwap': getattr(latest_bar, 'vwap', latest_bar.close)
                    }

            logger.warning(f"No data found for {symbol}")
            return None

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None

    async def get_multiple_bars(self, symbols: List[str]) -> Dict[str, Any]:
        """Get latest bars for multiple symbols"""
        results = {}

        # Process symbols in parallel
        tasks = [self.get_latest_bar(symbol) for symbol in symbols]
        bars_data = await asyncio.gather(*tasks, return_exceptions=True)

        for symbol, bar_data in zip(symbols, bars_data):
            if isinstance(bar_data, Exception):
                logger.error(f"Error getting data for {symbol}: {bar_data}")
                continue
            if bar_data:
                results[symbol] = bar_data

        return results

    def get_market_internals(self, symbols: List[str] = None) -> Dict[str, Any]:
        """Get market internals data (synchronous for compatibility)"""
        if symbols is None:
            symbols = self.key_symbols

        try:
            # Use a wider time range to get the most recent available data
            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)  # Last 7 days to ensure we get data

            request_params = StockBarsRequest(
                symbol_or_symbols=symbols,
                timeframe=TimeFrame.Day,  # Use daily data when market is closed
                start=start_time,
                end=end_time,
                limit=5  # Get last 5 days
            )

            bars = self.historical_client.get_stock_bars(request_params)

            if not bars.data:
                logger.warning("No bars data returned")
                return {}

            market_data = {}

            for symbol in symbols:
                if symbol in bars.data and len(bars.data[symbol]) > 0:
                    symbol_bars = bars.data[symbol]
                    latest_bar = symbol_bars[-1]
                    previous_bar = symbol_bars[-2] if len(symbol_bars) > 1 else None

                    # Calculate change and change percent
                    change = 0
                    change_pct = 0

                    if previous_bar:
                        change = latest_bar.close - previous_bar.close
                        change_pct = (change / previous_bar.close) * 100 if previous_bar.close != 0 else 0

                    market_data[symbol] = {
                        'price': float(latest_bar.close),
                        'change': float(change),
                        'change_pct': float(change_pct),
                        'volume': int(latest_bar.volume),
                        'timestamp': latest_bar.timestamp.isoformat() if latest_bar.timestamp else datetime.now().isoformat(),
                        'high': float(latest_bar.high),
                        'low': float(latest_bar.low),
                        'open': float(latest_bar.open)
                    }
                else:
                    logger.warning(f"No data available for {symbol}")

            return market_data

        except Exception as e:
            logger.error(f"Error getting market internals: {e}")
            return {}

    def get_macro_data(self) -> Dict[str, Any]:
        """Get macro economic indicators"""
        try:
            # Get macro data using ETF proxies
            macro_symbols = list(self.macro_symbols.values())
            symbol_mapping = {v: k for k, v in self.macro_symbols.items()}  # Reverse mapping

            # Use a wider time range to get the most recent available data
            end_time = datetime.now()
            start_time = end_time - timedelta(days=7)  # Last 7 days

            request_params = StockBarsRequest(
                symbol_or_symbols=macro_symbols,
                timeframe=TimeFrame.Day,  # Use daily data
                start=start_time,
                end=end_time,
                limit=5  # Get last 5 days
            )

            bars = self.historical_client.get_stock_bars(request_params)

            if not bars.data:
                logger.warning("No macro data returned")
                return {}

            macro_data = {}

            for etf_symbol in macro_symbols:
                if etf_symbol in bars.data and len(bars.data[etf_symbol]) > 0:
                    symbol_bars = bars.data[etf_symbol]
                    latest_bar = symbol_bars[-1]
                    previous_bar = symbol_bars[-2] if len(symbol_bars) > 1 else None

                    # Calculate change and change percent
                    change = 0
                    change_pct = 0

                    if previous_bar:
                        change = latest_bar.close - previous_bar.close
                        change_pct = (change / previous_bar.close) * 100 if previous_bar.close != 0 else 0

                    # Map back to original indicator name
                    indicator = symbol_mapping[etf_symbol]

                    macro_data[indicator] = {
                        'price': float(latest_bar.close),
                        'change': float(change),
                        'change_pct': float(change_pct),
                        'volume': int(latest_bar.volume),
                        'timestamp': latest_bar.timestamp.isoformat() if latest_bar.timestamp else datetime.now().isoformat()
                    }
                else:
                    logger.warning(f"No macro data available for {etf_symbol}")

            return macro_data

        except Exception as e:
            logger.error(f"Error getting macro data: {e}")
            return {}


# Convenience function for backward compatibility
def create_alpaca_client(settings: Settings) -> ModernAlpacaClient:
    """Create a modern Alpaca client instance"""
    return ModernAlpacaClient(settings)