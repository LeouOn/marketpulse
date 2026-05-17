"""Alpaca Market Data API Client
Replaces Yahoo Finance for stock market data
"""

from typing import Dict, Any, Optional, List
from datetime import datetime, timedelta
from loguru import logger

import aiohttp
from ..core.config import get_settings


class AlpacaClient:
    """Alpaca API client for real-time and historical market data"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.key_id = self.settings.api_keys.alpaca.key_id
        self.secret_key = self.settings.api_keys.alpaca.secret_key
        self.base_url = self.settings.api_keys.alpaca.base_url
        self.session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        headers = {
            'APCA-API-KEY-ID': self.key_id,
            'APCA-API-SECRET-KEY': self.secret_key
        }
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    async def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make GET request to Alpaca API"""
        try:
            url = f"{self.base_url}{endpoint}"
            async with self.session.get(url, params=params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    logger.error("Alpaca API authentication failed")
                elif response.status == 429:
                    logger.warning("Alpaca API rate limit hit")
                else:
                    logger.warning(f"Alpaca API error {response.status}: {await response.text()}")
                return None
        except Exception as e:
            logger.error(f"Alpaca API request failed: {e}")
            return None

    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time quote for a symbol"""
        data = await self._get(f"/v2/stocks/{symbol}/quotes/latest")
        if data and 'quote' in data:
            q = data['quote']
            return {
                'symbol': symbol,
                'price': float(q.get('ap', q.get('bp', 0))),
                'bid': float(q.get('ap', 0)),
                'ask': float(q.get('bp', 0)),
                'volume': int(q.get('v', 0)),
                'timestamp': q.get('t', datetime.now().isoformat())
            }
        return None

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get real-time quotes for multiple symbols"""
        result = {}
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                result[symbol] = quote
        return result

    async def get_bars(self, symbol: str, timeframe: str = "1Min",
                       start: datetime = None, end: datetime = None,
                       limit: int = 100) -> Optional[List[Dict]]:
        """Get historical OHLCV bars"""
        params = {
            'timeframe': timeframe,
            'limit': limit
        }
        if start:
            params['start'] = start.isoformat()
        if end:
            params['end'] = end.isoformat()

        data = await self._get(f"/v2/stocks/{symbol}/bars", params)
        if data and 'bars' in data:
            return [{
                'timestamp': bar['t'],
                'open': float(bar['o']),
                'high': float(bar['h']),
                'low': float(bar['l']),
                'close': float(bar['c']),
                'volume': int(bar['v']),
                'trade_count': int(bar['n'])
            } for bar in data['bars']]
        return None

    async def get_market_data(self, symbols: List[str]) -> Dict[str, Any]:
        """
        Get comprehensive market data for symbols (replacement for Yahoo Finance)
        Returns market internals format compatible with existing code
        """
        internals = {}
        for symbol in symbols:
            try:
                quote = await self.get_quote(symbol)
                if quote:
                    internals[symbol] = {
                        'price': quote['price'],
                        'bid': quote['bid'],
                        'ask': quote['ask'],
                        'change': 0,  # Need previous close for change
                        'change_pct': 0,
                        'volume': quote['volume'],
                        'timestamp': quote['timestamp']
                    }
            except Exception as e:
                logger.debug(f"Failed to get {symbol}: {e}")
                continue

        return internals

    async def get_snapshot(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get market snapshot for a symbol"""
        return await self._get(f"/v2/stocks/{symbol}/snapshot")

    async def is_available(self) -> bool:
        """Check if Alpaca API is accessible"""
        try:
            data = await self._get("/v2/account")
            return data is not None
        except:
            return False


async def get_alpaca_client() -> AlpacaClient:
    """Get Alpaca client instance"""
    return AlpacaClient()