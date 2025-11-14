"""Yahoo Finance API Client for MarketPulse
Uses Yahoo Finance for real-time market data (free and comprehensive)
"""

import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta
from typing import Dict, Any, List, Optional
from loguru import logger

from ..core.config import Settings


class YahooFinanceClient:
    """Yahoo Finance client for market data"""

    def __init__(self, settings: Settings = None):
        self.settings = settings

        # Market symbols to monitor
        self.market_symbols = [
            'SPY',    # S&P 500 ETF
            'QQQ',    # NASDAQ ETF
            '^VIX',   # VIX Volatility Index - Fixed with ^ prefix
            'IWM',    # Russell 2000 ETF
            'DIA',    # Dow Jones ETF
            'VTI',    # Total Stock Market ETF
            'VOO',    # Vanguard S&P 500 ETF
            'AAPL',   # Apple
            'TSLA',   # Tesla
            'NVDA'    # NVIDIA
        ]

        # Macro indicators using ETFs
        self.macro_symbols = {
            'DXY': 'UUP',   # US Dollar Index ETF
            'GC': 'GLD',    # Gold ETF
            'CL': 'USO',    # Oil ETF
            'TNX': '^TNX',  # 10-Year Treasury Yield (^TNX)
            'BTC': 'BTC-USD',  # Bitcoin
            'ETH': 'ETH-USD',  # Ethereum
            'SOL': 'SOL-USD',  # Solana
            'XRP': 'XRP-USD'   # Ripple
        }

    def get_market_internals(self, symbols: List[str] = None, timeframe: str = '1d', period: str = '2d') -> Dict[str, Any]:
        """Get market data for specified symbols

        Args:
            symbols: List of symbols to fetch
            timeframe: '1d' (default), '1h', '4h', '5m', '15m', etc.
            period: '1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max'
        """
        if symbols is None:
            symbols = self.market_symbols

        try:
            # Map timeframe to appropriate Yahoo Finance interval
            interval_map = {
                '1m': '1m',
                '2m': '2m',
                '5m': '5m',
                '15m': '15m',
                '30m': '30m',
                '1h': '1h',
                '4h': '1d',  # Yahoo Finance doesn't have 4h, use 1d for longer periods
                '1d': '1d',
                '1w': '1wk',
                '1mo': '1mo'
            }

            # Map period strings
            period_map = {
                '4h': '5d',
                '1d': '2d',
                '7d': '7d',
                '1m': '1mo',
                '3m': '3mo',
                '6m': '6mo',
                '1y': '1y'
            }

            # Use mapped values
            interval = interval_map.get(timeframe, '1d')
            data_period = period_map.get(period, period)

            data = yf.download(
                symbols,
                period=data_period,
                interval=interval,
                progress=False,
                auto_adjust=False  # Get raw prices
            )

            if data.empty or 'Close' not in data:
                logger.warning("No data returned from Yahoo Finance")
                return {}

            market_data = {}

            for symbol in symbols:
                try:
                    if symbol in data['Close'].columns:
                        close_prices = data['Close'][symbol].dropna()
                        volumes = data['Volume'][symbol].dropna() if 'Volume' in data else pd.Series()

                        if len(close_prices) > 0:
                            latest_price = close_prices.iloc[-1]
                            latest_volume = volumes.iloc[-1] if len(volumes) > 0 else 0

                            # Calculate change and change percent
                            change = 0.0
                            change_pct = 0.0

                            if len(close_prices) > 1:
                                prev_price = close_prices.iloc[-2]
                                change = latest_price - prev_price
                                change_pct = (change / prev_price) * 100 if prev_price != 0 else 0

                            # Get high and low if available
                            high_price = data['High'][symbol].iloc[-1] if 'High' in data and symbol in data['High'].columns else latest_price
                            low_price = data['Low'][symbol].iloc[-1] if 'Low' in data and symbol in data['Low'].columns else latest_price
                            open_price = data['Open'][symbol].iloc[-1] if 'Open' in data and symbol in data['Open'].columns else latest_price

                            market_data[symbol] = {
                                'price': float(latest_price),
                                'change': float(change),
                                'change_pct': float(change_pct),
                                'volume': int(latest_volume) if pd.notna(latest_volume) else 0,
                                'timestamp': datetime.now().isoformat(),
                                'high': float(high_price),
                                'low': float(low_price),
                                'open': float(open_price)
                            }
                        else:
                            logger.warning(f"No price data available for {symbol}")
                    else:
                        logger.warning(f"Symbol {symbol} not found in Yahoo Finance data")

                except Exception as e:
                    logger.error(f"Error processing data for {symbol}: {e}")
                    continue

            logger.info(f"Successfully retrieved data for {len(market_data)} symbols")
            return market_data

        except Exception as e:
            logger.error(f"Error fetching market data from Yahoo Finance: {e}")
            return {}

    def get_macro_data(self) -> Dict[str, Any]:
        """Get macro economic indicators"""
        try:
            # Get macro ETF symbols
            etf_symbols = [sym for sym in self.macro_symbols.values() if not sym.startswith('^')]
            crypto_symbols = [sym for sym in self.macro_symbols.values() if sym.endswith('-USD')]

            all_symbols = etf_symbols + crypto_symbols

            macro_data = {}

            # Download ETF and crypto data separately
            # First download ETF data
            if etf_symbols:
                etf_data = yf.download(
                    etf_symbols,
                    period='2d',
                    interval='1d',
                    progress=False,
                    auto_adjust=False
                )

                if not etf_data.empty and 'Close' in etf_data:
                    for etf_symbol in etf_symbols:
                        try:
                            if etf_symbol in etf_data['Close'].columns:
                                close_prices = etf_data['Close'][etf_symbol].dropna()
                                volumes = etf_data['Volume'][etf_symbol].dropna() if 'Volume' in etf_data else pd.Series()

                                if len(close_prices) > 0:
                                    latest_price = close_prices.iloc[-1]
                                    latest_volume = volumes.iloc[-1] if len(volumes) > 0 else 0

                                    # Calculate change
                                    change = 0.0
                                    change_pct = 0.0
                                    if len(close_prices) > 1:
                                        prev_price = close_prices.iloc[-2]
                                        change = latest_price - prev_price
                                        change_pct = (change / prev_price) * 100 if prev_price != 0 else 0

                                    # Map back to indicator name
                                    indicator = None
                                    for ind, sym in self.macro_symbols.items():
                                        if sym == etf_symbol:
                                            indicator = ind
                                            break

                                    if indicator:
                                        macro_data[indicator] = {
                                            'price': float(latest_price),
                                            'change': float(change),
                                            'change_pct': float(change_pct),
                                            'volume': int(latest_volume) if pd.notna(latest_volume) else 0,
                                            'timestamp': datetime.now().isoformat()
                                        }

                        except Exception as e:
                            logger.debug(f"Error processing ETF {etf_symbol}: {e}")

            # Then download crypto data with more history for change calculation
            if crypto_symbols:
                crypto_data = yf.download(
                    crypto_symbols,
                    period='7d',  # Get 7 days to ensure we have previous day data
                    interval='1d',
                    progress=False,
                    auto_adjust=False
                )

                if not crypto_data.empty and 'Close' in crypto_data:
                    for crypto_symbol in crypto_symbols:
                        try:
                            if crypto_symbol in crypto_data['Close'].columns:
                                close_prices = crypto_data['Close'][crypto_symbol].dropna()
                                volumes = crypto_data['Volume'][crypto_symbol].dropna() if 'Volume' in crypto_data else pd.Series()

                                if len(close_prices) > 0:
                                    latest_price = close_prices.iloc[-1]
                                    latest_volume = volumes.iloc[-1] if len(volumes) > 0 else 0

                                    # Calculate change
                                    change = 0.0
                                    change_pct = 0.0
                                    if len(close_prices) > 1:
                                        prev_price = close_prices.iloc[-2]
                                        change = latest_price - prev_price
                                        change_pct = (change / prev_price) * 100 if prev_price != 0 else 0

                                    # Map back to indicator name
                                    indicator = None
                                    for ind, sym in self.macro_symbols.items():
                                        if sym == crypto_symbol:
                                            indicator = ind
                                            break

                                    if indicator:
                                        macro_data[indicator] = {
                                            'price': float(latest_price),
                                            'change': float(change),
                                            'change_pct': float(change_pct),
                                            'volume': int(latest_volume) if pd.notna(latest_volume) else 0,
                                            'timestamp': datetime.now().isoformat()
                                        }

                        except Exception as e:
                            logger.debug(f"Error processing crypto {crypto_symbol}: {e}")

            # Handle treasury yield (^TNX) separately if needed
            try:
                tnx_data = yf.download('^TNX', period='2d', interval='1d', progress=False, auto_adjust=False)
                if not tnx_data.empty and 'Close' in tnx_data:
                    close_prices = tnx_data['Close'].dropna()
                    if len(close_prices) > 0:
                        latest_yield = close_prices.iloc[-1]
                        change = 0.0
                        if len(close_prices) > 1:
                            prev_yield = close_prices.iloc[-2]
                            change = latest_yield - prev_yield

                        macro_data['TNX'] = {
                            'price': float(latest_yield.iloc[0] if hasattr(latest_yield, 'iloc') else latest_yield),
                            'change': float(change.iloc[0] if hasattr(change, 'iloc') else change),
                            'change_pct': float(change.iloc[0] if hasattr(change, 'iloc') else change),  # For yields, change is already in percentage points
                            'volume': 0,
                            'timestamp': datetime.now().isoformat()
                        }
            except Exception as e:
                logger.debug(f"Could not fetch TNX data: {e}")

            logger.info(f"Successfully retrieved macro data for {len(macro_data)} indicators")
            return macro_data

        except Exception as e:
            logger.error(f"Error fetching macro data from Yahoo Finance: {e}")
            return {}

    def get_single_symbol_data(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get data for a single symbol"""
        try:
            ticker = yf.Ticker(symbol)
            hist = ticker.history(period='2d', interval='1d')

            if hist.empty:
                return None

            latest = hist.iloc[-1]
            previous = hist.iloc[-2] if len(hist) > 1 else None

            price = float(latest['Close'])
            volume = int(latest['Volume'])

            change = 0.0
            change_pct = 0.0
            if previous is not None:
                change = price - float(previous['Close'])
                change_pct = (change / float(previous['Close'])) * 100

            return {
                'symbol': symbol,
                'price': price,
                'change': change,
                'change_pct': change_pct,
                'volume': volume,
                'timestamp': datetime.now().isoformat(),
                'high': float(latest['High']),
                'low': float(latest['Low']),
                'open': float(latest['Open'])
            }

        except Exception as e:
            logger.error(f"Error fetching data for {symbol}: {e}")
            return None


# Convenience function
def create_yahoo_client(settings: Settings = None) -> YahooFinanceClient:
    """Create a Yahoo Finance client instance"""
    return YahooFinanceClient(settings)