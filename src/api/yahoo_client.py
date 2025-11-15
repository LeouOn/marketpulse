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
            'NQ=F',   # Nasdaq 100 Futures
            'ES=F',   # S&P 500 Futures
            'IWM',    # Russell 2000 ETF
            'DIA',    # Dow Jones ETF
            'VTI',    # Total Stock Market ETF
            'VOO',    # Vanguard S&P 500 ETF
            'AAPL',   # Apple
            'TSLA',   # Tesla
            'NVDA'    # NVIDIA
        ]

        # Macro indicators using ETFs and direct symbols
        self.macro_symbols = {
            # Commodities & Indices
            'DXY': 'UUP',   # US Dollar Index ETF
            'GC': 'GLD',    # Gold ETF
            'CL': 'CL=F',   # Crude Oil Futures (WTI) - Direct symbol
            'TNX': '^TNX',  # 10-Year Treasury Yield (^TNX)

            # Cryptocurrencies
            'BTC': 'BTC-USD',  # Bitcoin
            'ETH': 'ETH-USD',  # Ethereum
            'SOL': 'SOL-USD',  # Solana
            'XRP': 'XRP-USD',  # Ripple

            # Asian Markets
            'NIKKEI': '^N225',     # Nikkei 225 (Japan)
            'HSI': '^HSI',         # Hang Seng (Hong Kong)
            'SSE': '000001.SS',    # Shanghai Composite (China)
            'ASX': '^AXJO',        # ASX 200 (Australia)

            # European Markets
            'FTSE': '^FTSE',       # FTSE 100 (UK)
            'DAX': '^GDAXI',       # DAX (Germany)
            'CAC': '^FCHI',        # CAC 40 (France)
            'STOXX': '^STOXX50E',  # Euro Stoxx 50

            # Forex (Major Pairs)
            'EURUSD': 'EURUSD=X',  # Euro / US Dollar
            'GBPUSD': 'GBPUSD=X',  # British Pound / US Dollar
            'USDJPY': 'USDJPY=X',  # US Dollar / Japanese Yen
            'AUDUSD': 'AUDUSD=X',  # Australian Dollar / US Dollar
            'USDCAD': 'USDCAD=X',  # US Dollar / Canadian Dollar
            'USDCHF': 'USDCHF=X',  # US Dollar / Swiss Franc
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
            # Categorize symbols by type for efficient batch fetching
            etf_symbols = []
            crypto_symbols = []
            index_symbols = []
            forex_symbols = []
            futures_symbols = []

            for indicator, symbol in self.macro_symbols.items():
                if symbol.endswith('-USD'):
                    crypto_symbols.append(symbol)
                elif symbol.startswith('^'):
                    index_symbols.append(symbol)
                elif symbol.endswith('=X'):
                    forex_symbols.append(symbol)
                elif symbol.endswith('=F'):
                    futures_symbols.append(symbol)
                else:
                    etf_symbols.append(symbol)

            macro_data = {}

            # Helper function to process symbol data
            def process_symbol_data(data, symbols_list, period_days='2d'):
                if data.empty or 'Close' not in data:
                    return

                for symbol in symbols_list:
                    try:
                        # Handle both multi-index (multiple symbols) and single symbol DataFrames
                        if symbol in data['Close'].columns:
                            close_prices = data['Close'][symbol].dropna()
                        elif hasattr(data['Close'], 'name'):  # Single symbol
                            close_prices = data['Close'].dropna()
                        else:
                            continue

                        if len(close_prices) == 0:
                            continue

                        # Get volumes (may not exist for all asset types)
                        volumes = pd.Series()
                        if 'Volume' in data:
                            if symbol in data['Volume'].columns:
                                volumes = data['Volume'][symbol].dropna()
                            elif hasattr(data['Volume'], 'name'):
                                volumes = data['Volume'].dropna()

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
                            if sym == symbol:
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
                        logger.debug(f"Error processing {symbol}: {e}")

            # Fetch ETF data
            if etf_symbols:
                try:
                    etf_data = yf.download(
                        etf_symbols,
                        period='2d',
                        interval='1d',
                        progress=False,
                        auto_adjust=False
                    )
                    process_symbol_data(etf_data, etf_symbols)
                except Exception as e:
                    logger.debug(f"Error fetching ETF data: {e}")

            # Fetch crypto data (needs more history)
            if crypto_symbols:
                try:
                    crypto_data = yf.download(
                        crypto_symbols,
                        period='7d',
                        interval='1d',
                        progress=False,
                        auto_adjust=False
                    )
                    process_symbol_data(crypto_data, crypto_symbols, '7d')
                except Exception as e:
                    logger.debug(f"Error fetching crypto data: {e}")

            # Fetch index data (^VIX, ^N225, ^HSI, etc.)
            if index_symbols:
                try:
                    index_data = yf.download(
                        index_symbols,
                        period='2d',
                        interval='1d',
                        progress=False,
                        auto_adjust=False
                    )
                    process_symbol_data(index_data, index_symbols)
                except Exception as e:
                    logger.debug(f"Error fetching index data: {e}")

            # Fetch forex data (EURUSD=X, etc.)
            if forex_symbols:
                try:
                    forex_data = yf.download(
                        forex_symbols,
                        period='2d',
                        interval='1d',
                        progress=False,
                        auto_adjust=False
                    )
                    process_symbol_data(forex_data, forex_symbols)
                except Exception as e:
                    logger.debug(f"Error fetching forex data: {e}")

            # Fetch futures data (CL=F, etc.)
            if futures_symbols:
                try:
                    futures_data = yf.download(
                        futures_symbols,
                        period='2d',
                        interval='1d',
                        progress=False,
                        auto_adjust=False
                    )
                    process_symbol_data(futures_data, futures_symbols)
                except Exception as e:
                    logger.debug(f"Error fetching futures data: {e}")

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


    def get_bars(self, symbol: str, period: str = '1mo', interval: str = '1d') -> Optional[pd.DataFrame]:
        """Get historical OHLC data for a symbol

        Args:
            symbol: Stock symbol (e.g., 'SPY', 'AAPL', 'BTC')
            period: Period string ('1d', '5d', '1mo', '3mo', '6mo', '1y', '2y', '5y', '10y', 'ytd', 'max')
            interval: Data interval ('1m', '2m', '5m', '15m', '30m', '60m', '90m', '1h', '1d', '5d', '1wk', '1mo', '3mo')
        """
        try:
            # Map symbol if it's in macro_symbols (e.g., BTC -> BTC-USD)
            yahoo_symbol = self.macro_symbols.get(symbol, symbol)

            # Download historical data from Yahoo Finance
            data = yf.download(
                yahoo_symbol,
                period=period,
                interval=interval,
                progress=False,
                auto_adjust=False
            )

            if data.empty:
                logger.warning(f"No historical data found for {symbol}")
                return None

            # Rename columns to standard format
            if 'Close' in data.columns:
                data = data.rename(columns={
                    'Close': 'close',
                    'Open': 'open',
                    'High': 'high',
                    'Low': 'low',
                    'Volume': 'volume'
                })

            # Ensure we have the required columns
            required_columns = ['open', 'high', 'low', 'close', 'volume']
            if not all(col in data.columns for col in required_columns):
                logger.error(f"Missing required columns in data for {symbol}")
                return None

            return data

        except Exception as e:
            logger.error(f"Error fetching bars for {symbol}: {e}")
            return None

# Convenience function
def create_yahoo_client(settings: Settings = None) -> YahooFinanceClient:
    """Create a Yahoo Finance client instance"""
    return YahooFinanceClient(settings)