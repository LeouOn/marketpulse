"""Rithmic Futures Data API Client
Provides real-time futures data (NQ, ES, etc.)
"""

from typing import Dict, Any, Optional, List
from datetime import datetime
from loguru import logger
import json
import asyncio

import aiohttp
from ..core.config import get_settings


class RithmicClient:
    """Rithmic API client for futures market data"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.username = self.settings.api_keys.rithmic.username
        self.password = self.settings.api_keys.rithmic.password
        self.system_name = self.settings.api_keys.rithmic.system_name
        self.login_prefix = self.settings.api_keys.rithmic.login_prefix
        self.base_url = "https://api.rithmic.com"  # Rithmic REST API base
        self.session: Optional[aiohttp.ClientSession] = None
        self._connected = False
        self._ws: Optional[aiohttp.ClientWebSocketResponse] = None

    async def __aenter__(self):
        headers = {
            'Content-Type': 'application/json'
        }
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(headers=headers, timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.disconnect()
        if self.session:
            await self.session.close()

    async def connect(self) -> bool:
        """Connect to Rithmic"""
        try:
            login_url = f"{self.base_url}/auth/login"
            payload = {
                'user': self.username,
                'password': self.password,
                'system': self.system_name,
                'login_prefix': self.login_prefix
            }
            async with self.session.post(login_url, json=payload) as resp:
                if resp.status == 200:
                    data = await resp.json()
                    self._token = data.get('token')
                    self._connected = True
                    logger.success("Rithmic connected")
                    return True
                else:
                    logger.error(f"Rithmic auth failed: {resp.status}")
                    return False
        except Exception as e:
            logger.error(f"Rithmic connection error: {e}")
            return False

    async def disconnect(self):
        """Disconnect from Rithmic"""
        if self._ws:
            await self._ws.close()
        self._connected = False

    async def _get(self, endpoint: str, params: Dict = None) -> Optional[Dict]:
        """Make authenticated GET request"""
        if not self._connected:
            return None
        try:
            headers = {'Authorization': f'Bearer {self._token}'}
            url = f"{self.base_url}{endpoint}"
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logger.debug(f"Rithmic API error: {e}")
            return None

    async def get_quote(self, symbol: str) -> Optional[Dict[str, Any]]:
        """Get real-time quote for futures symbol"""
        data = await self._get(f"/quotes/{symbol}")
        if data:
            return {
                'symbol': symbol,
                'bid': float(data.get('bid', 0)),
                'ask': float(data.get('ask', 0)),
                'last': float(data.get('last', 0)),
                'volume': int(data.get('volume', 0)),
                'timestamp': data.get('timestamp', datetime.now().isoformat())
            }
        return None

    async def get_quotes(self, symbols: List[str]) -> Dict[str, Dict]:
        """Get quotes for multiple symbols"""
        result = {}
        for symbol in symbols:
            quote = await self.get_quote(symbol)
            if quote:
                result[symbol] = quote
        return result

    async def get_ohlc(self, symbol: str, timeframe: str = "1min",
                       start: datetime = None, end: datetime = None,
                       limit: int = 100) -> Optional[List[Dict]]:
        """Get historical OHLCV data for futures"""
        params = {
            'symbol': symbol,
            'timeframe': timeframe,
            'limit': limit
        }
        if start:
            params['start'] = start.isoformat()
        if end:
            params['end'] = end.isoformat()

        data = await self._get("/bars", params)
        if data and 'bars' in data:
            return [{
                'timestamp': bar['t'],
                'open': float(bar['o']),
                'high': float(bar['h']),
                'low': float(bar['l']),
                'close': float(bar['c']),
                'volume': int(bar['v'])
            } for bar in data['bars']]
        return None

    async def get_futures_data(self, symbols: List[str]) -> Dict[str, Any]:
        """Get futures market data in standard format"""
        internals = {}
        for symbol in symbols:
            try:
                quote = await self.get_quote(symbol)
                if quote:
                    internals[symbol] = {
                        'price': quote['last'],
                        'bid': quote['bid'],
                        'ask': quote['ask'],
                        'change': 0,
                        'change_pct': 0,
                        'volume': quote['volume'],
                        'timestamp': quote['timestamp']
                    }
            except Exception as e:
                logger.debug(f"Rithmic failed for {symbol}: {e}")
                continue
        return internals

    async def is_available(self) -> bool:
        """Check if Rithmic is accessible"""
        if not self._connected:
            return False
        try:
            data = await self._get("/health")
            return data is not None
        except:
            return False


async def get_rithmic_client() -> RithmicClient:
    """Get Rithmic client instance"""
    client = RithmicClient()
    await client.connect()
    return client