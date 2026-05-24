"""Coinbase Cryptocurrency Data API Client
Provides real-time crypto market data (BTC, ETH, etc.)
"""

import base64
import hashlib
import hmac
import json
import time
from datetime import datetime
from typing import Any

import aiohttp
from loguru import logger

from ..core.config import get_settings


class CoinbaseClient:
    """Coinbase API client for cryptocurrency market data"""

    def __init__(self, settings=None):
        self.settings = settings or get_settings()
        self.api_key = self.settings.api_keys.coinbase.api_key
        self.api_secret = self.settings.api_keys.coinbase.api_secret
        self.passphrase = self.settings.api_keys.coinbase.passphrase
        self.base_url = "https://api.coinbase.com"
        self.session: aiohttp.ClientSession | None = None

    async def __aenter__(self):
        timeout = aiohttp.ClientTimeout(total=30)
        self.session = aiohttp.ClientSession(timeout=timeout)
        return self

    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()

    def _sign_request(self, method: str, path: str, body: str = "") -> dict[str, str]:
        """Generate Coinbase API signature"""
        timestamp = str(int(time.time()))
        message = timestamp + method + path + body
        key = base64.b64decode(self.api_secret)
        signature = hmac.new(key, message.encode(), hashlib.sha256)
        return {
            "CB-ACCESS-KEY": self.api_key,
            "CB-ACCESS-SIGN": base64.b64encode(signature.digest()).decode(),
            "CB-ACCESS-TIMESTAMP": timestamp,
            "CB-ACCESS-PASSPHRASE": self.passphrase,
        }

    async def _get(self, endpoint: str, params: dict = None) -> dict | None:
        """Make GET request to Coinbase API"""
        try:
            path = endpoint
            headers = self._sign_request("GET", path)
            url = f"{self.base_url}{path}"
            async with self.session.get(url, headers=headers, params=params) as response:
                if response.status == 200:
                    return await response.json()
                elif response.status == 401:
                    logger.error("Coinbase API authentication failed")
                elif response.status == 429:
                    logger.warning("Coinbase API rate limit hit")
                return None
        except Exception as e:
            logger.debug(f"Coinbase API error: {e}")
            return None

    async def _post(self, endpoint: str, data: dict = None) -> dict | None:
        """Make POST request to Coinbase API"""
        try:
            path = endpoint
            body = json.dumps(data) if data else ""
            headers = self._sign_request("POST", path, body)
            url = f"{self.base_url}{path}"
            async with self.session.post(url, headers=headers, json=data) as response:
                if response.status == 200:
                    return await response.json()
                return None
        except Exception as e:
            logger.debug(f"Coinbase API error: {e}")
            return None

    async def get_price(self, symbol: str) -> dict[str, Any] | None:
        """
        Get current price for a crypto symbol
        symbol format: 'BTC-USD', 'ETH-USD'
        """
        data = await self._get(f"/v2/prices/{symbol}/spot")
        if data and "data" in data:
            return {"symbol": symbol, "price": float(data["data"]["amount"]), "timestamp": datetime.now().isoformat()}
        return None

    async def get_prices(self, symbols: list[str]) -> dict[str, dict]:
        """Get prices for multiple crypto symbols"""
        result = {}
        for symbol in symbols:
            price = await self.get_price(symbol)
            if price:
                result[symbol] = price
        return result

    async def get_candles(
        self, symbol: str, granularity: int = 3600, start: datetime = None, end: datetime = None
    ) -> list[dict] | None:
        """
        Get OHLCV candles for crypto
        granularity: 60, 300, 900, 3600, 21600, 86400 (seconds)
        """
        params = {"granularity": granularity}
        if start:
            params["start"] = start.isoformat() + "Z"
        if end:
            params["end"] = end.isoformat() + "Z"

        data = await self._get(f"/v2/products/{symbol}/candles", params)
        if data and isinstance(data, list):
            return [
                {
                    "timestamp": candle[0],
                    "low": float(candle[1]),
                    "high": float(candle[2]),
                    "open": float(candle[3]),
                    "close": float(candle[4]),
                    "volume": float(candle[5]),
                }
                for candle in data
            ]
        return None

    async def get_ticker(self, symbol: str) -> dict[str, Any] | None:
        """Get ticker data for crypto symbol"""
        data = await self._get(f"/v2/products/{symbol}/ticker")
        if data and "data" in data:
            t = data["data"]
            return {
                "symbol": symbol,
                "price": float(t["price"]),
                "bid": float(t["bid"]),
                "ask": float(t["ask"]),
                "volume": float(t["volume"]),
                "timestamp": t.get("time", datetime.now().isoformat()),
            }
        return None

    async def get_market_data(self, symbols: list[str]) -> dict[str, Any]:
        """
        Get comprehensive market data for crypto symbols
        Returns format compatible with existing market internals
        """
        internals = {}
        for symbol in symbols:
            try:
                ticker = await self.get_ticker(symbol)
                if ticker:
                    internals[symbol] = {
                        "price": ticker["price"],
                        "bid": ticker["bid"],
                        "ask": ticker["ask"],
                        "change": 0,  # Would need previous close for change
                        "change_pct": 0,
                        "volume": int(ticker["volume"]),
                        "timestamp": ticker["timestamp"],
                    }
            except Exception as e:
                logger.debug(f"Coinbase failed for {symbol}: {e}")
                continue
        return internals

    async def is_available(self) -> bool:
        """Check if Coinbase API is accessible"""
        try:
            data = await self._get("/v2/time")
            return data is not None
        except:
            return False


async def get_coinbase_client() -> CoinbaseClient:
    """Get Coinbase client instance"""
    return CoinbaseClient()
