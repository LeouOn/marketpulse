"""Market Data Collector - Unified Client
Orchestrates data collection from Alpaca, Rithmic, Coinbase, Yahoo Finance with Redis caching
"""

from datetime import datetime
from typing import Any

from loguru import logger

from ..core.cache import CacheService, get_cache
from ..core.config import get_settings
from .alpaca_client import AlpacaClient, get_alpaca_client
from .coinbase_client import CoinbaseClient, get_coinbase_client
from .rithmic_client import RithmicClient, get_rithmic_client
from .yahoo_client import YahooFinanceClient


class MarketDataCollector:
    """Unified market data collector with caching and fallbacks"""

    def __init__(self):
        self.settings = get_settings()
        self.alpaca: AlpacaClient | None = None
        self.rithmic: RithmicClient | None = None
        self.coinbase: CoinbaseClient | None = None
        self.yahoo: YahooFinanceClient | None = None
        self.cache: CacheService | None = None

        self.symbols = {
            "stocks": ["SPY", "QQQ", "IWM"],
            "futures": ["NQ=F"],
            "crypto": ["BTC-USD", "ETH-USD"],
            "indices": ["^VIX"],
        }

        self.all_symbols = ["SPY", "QQQ", "IWM", "NQ=F", "BTC-USD", "ETH-USD", "^VIX"]

    async def initialize(self) -> bool:
        """Initialize all clients and cache"""
        logger.info("Initializing Market Data Collector...")

        try:
            self.cache = await get_cache()
            logger.success("Cache initialized")
        except Exception as e:
            logger.warning(f"Cache init failed: {e}")

        # Initialize Yahoo Finance (always available, free)
        try:
            self.yahoo = YahooFinanceClient(self.settings)
            logger.success("Yahoo Finance initialized")
        except Exception as e:
            logger.warning(f"Yahoo Finance init failed: {e}")

        # Initialize Alpaca (stocks)
        try:
            self.alpaca = await get_alpaca_client()
            if await self.alpaca.is_available():
                logger.success("Alpaca connected")
            else:
                logger.warning("Alpaca unavailable")
                self.alpaca = None
        except Exception as e:
            logger.warning(f"Alpaca init failed: {e}")
            self.alpaca = None

        # Initialize Rithmic (futures)
        try:
            self.rithmic = await get_rithmic_client()
            if await self.rithmic.is_available():
                logger.success("Rithmic connected")
            else:
                logger.warning("Rithmic unavailable")
                self.rithmic = None
        except Exception as e:
            logger.warning(f"Rithmic init failed: {e}")
            self.rithmic = None

        # Initialize Coinbase (crypto)
        try:
            self.coinbase = await get_coinbase_client()
            if await self.coinbase.is_available():
                logger.success("Coinbase connected")
            else:
                logger.warning("Coinbase unavailable")
                self.coinbase = None
        except Exception as e:
            logger.warning(f"Coinbase init failed: {e}")
            self.coinbase = None

        return True

    async def get_stocks_data(self, symbols: list[str]) -> dict[str, Any]:
        """Get stock data from Alpaca"""
        if not self.alpaca:
            return {}

        try:
            return await self.alpaca.get_market_data(symbols)
        except Exception as e:
            logger.error(f"Alpaca stocks error: {e}")
            return {}

    async def get_futures_data(self, symbols: list[str]) -> dict[str, Any]:
        """Get futures data from Rithmic"""
        if not self.rithmic:
            return {}

        try:
            return await self.rithmic.get_futures_data(symbols)
        except Exception as e:
            logger.error(f"Rithmic futures error: {e}")
            return {}

    async def get_crypto_data(self, symbols: list[str]) -> dict[str, Any]:
        """Get crypto data from Coinbase"""
        if not self.coinbase:
            return {}

        try:
            return await self.coinbase.get_market_data(symbols)
        except Exception as e:
            logger.error(f"Coinbase crypto error: {e}")
            return {}

    async def get_all_market_data(self, use_cache: bool = True) -> dict[str, Any]:
        """
        Collect all market data with caching

        Returns unified market internals format
        Priority: Alpaca > Rithmic > Coinbase > Yahoo Finance > Mock
        """
        cache_key = "all_market_data"

        if use_cache and self.cache:
            cached = await self.cache.get(cache_key)
            if cached:
                logger.debug("Cache hit for market data")
                return cached

        internals = {}
        sources_used = []

        # Try Alpaca for stocks
        stocks = await self.get_stocks_data(self.symbols["stocks"])
        if stocks:
            internals.update(stocks)
            sources_used.append("alpaca")

        # Try Rithmic for futures
        futures = await self.get_futures_data(self.symbols["futures"])
        if futures:
            internals.update(futures)
            sources_used.append("rithmic")

        # Try Coinbase for crypto
        crypto = await self.get_crypto_data(self.symbols["crypto"])
        if crypto:
            internals.update(crypto)
            sources_used.append("coinbase")

        # If all external APIs failed, fall back to Yahoo Finance
        if not internals or len(internals) < 3:
            logger.warning("External APIs unavailable, falling back to Yahoo Finance")
            if self.yahoo:
                try:
                    yahoo_data = self.yahoo.get_market_internals(self.all_symbols)
                    if yahoo_data:
                        internals.update(yahoo_data)
                        sources_used.append("yahoo")
                        logger.info("Yahoo Finance fallback successful")
                except Exception as e:
                    logger.error(f"Yahoo Finance fallback failed: {e}")

        # Final fallback to mock data
        if not internals or len(internals) < 3:
            logger.warning("All data sources failed, using mock data")
            from .mock_market import mock_provider

            internals = await mock_provider.get_market_internals()
            internals["data_source"] = "mock"
        else:
            internals["data_source"] = ",".join(sources_used) if sources_used else "unknown"

        internals["timestamp"] = datetime.now().isoformat()

        if use_cache and self.cache and internals:
            await self.cache.set(cache_key, internals, ttl_seconds=30)

        return internals

    async def get_ohlc_data(self, symbol: str, timeframe: str = "1Min", use_cache: bool = True) -> list[dict] | None:
        """Get OHLCV data for a symbol"""
        cache_key = f"ohlc:{symbol}:{timeframe}"

        if use_cache and self.cache:
            cached = await self.cache.get_ohlc(symbol, timeframe)
            if cached:
                return cached

        data = None

        if symbol in self.symbols["stocks"] and self.alpaca:
            data = await self.alpaca.get_bars(symbol, timeframe, limit=100)

        if symbol == "NQ=F" and self.rithmic:
            rithmic_symbol = "NQ" if symbol == "NQ=F" else symbol
            data = await self.rithmic.get_ohlc(rithmic_symbol, timeframe, limit=100)

        if ("-USD" in symbol or "-USD" in symbol) and self.coinbase:
            data = await self.coinbase.get_candles(symbol, granularity=60, limit=100)

        if data and self.cache:
            await self.cache.set_ohlc(symbol, timeframe, data)

        return data

    async def health_check(self) -> dict[str, Any]:
        """Check health of all data sources"""
        return {
            "alpaca": self.alpaca is not None and await self.alpaca.is_available(),
            "rithmic": self.rithmic is not None and await self.rithmic.is_available(),
            "coinbase": self.coinbase is not None and await self.coinbase.is_available(),
            "cache": self.cache is not None and self.cache.is_connected,
        }


_collector_instance: MarketDataCollector | None = None


async def get_collector() -> MarketDataCollector:
    """Get or create market data collector"""
    global _collector_instance
    if _collector_instance is None:
        _collector_instance = MarketDataCollector()
        await _collector_instance.initialize()
    return _collector_instance
