"""MarketPulse Redis Cache Service
Provides caching layer for market data to reduce API calls
"""

import asyncio
import json
from typing import Any

import redis.asyncio as redis
from loguru import logger

from ..core.config import get_settings


class CacheService:
    """Redis-based caching service for MarketPulse"""

    def __init__(self):
        self.settings = get_settings()
        self._client: redis.Redis | None = None
        self._connected = False

        # Default TTLs
        self.ttl_market_internals = 30  # 30 seconds for real-time data
        self.ttl_ohlc = 300  # 5 minutes for OHLC data
        self.ttl_breadth = 60  # 1 minute for breadth indicators
        self.ttl_llm_response = 600  # 10 minutes for LLM responses

    async def connect(self) -> bool:
        """Connect to Redis"""
        try:
            self._client = redis.Redis(
                host=self.settings.redis_host,
                port=self.settings.redis_port,
                db=self.settings.redis_db,
                password=self.settings.redis_password or None,
                decode_responses=True,
                socket_connect_timeout=2,
                socket_timeout=2,
            )
            await asyncio.wait_for(self._client.ping(), timeout=3)
            self._connected = True
            logger.success(f"Redis connected at {self.settings.redis_host}:{self.settings.redis_port}")
            return True
        except Exception as e:
            logger.warning(f"Redis connection failed: {e}. Caching disabled.")
            self._connected = False
            return False

    async def disconnect(self):
        """Disconnect from Redis"""
        if self._client:
            await self._client.close()
            self._connected = False

    @property
    def is_connected(self) -> bool:
        return self._connected and self._client is not None

    async def get(self, key: str) -> Any | None:
        """Get value from cache"""
        if not self.is_connected:
            return None
        try:
            value = await self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.debug(f"Cache get error for {key}: {e}")
            return None

    async def set(self, key: str, value: Any, ttl_seconds: int = 60) -> bool:
        """Set value in cache with TTL"""
        if not self.is_connected:
            return False
        try:
            serialized = json.dumps(value, default=str)
            await self._client.setex(key, ttl_seconds, serialized)
            return True
        except Exception as e:
            logger.debug(f"Cache set error for {key}: {e}")
            return False

    async def delete(self, key: str) -> bool:
        """Delete key from cache"""
        if not self.is_connected:
            return False
        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.debug(f"Cache delete error for {key}: {e}")
            return False

    async def get_or_set(self, key: str, fetch_func, ttl_seconds: int = 60) -> Any | None:
        """
        Get from cache or fetch and cache if missing
        Args:
            key: Cache key
            fetch_func: Async function to fetch data if cache miss
            ttl_seconds: TTL for cached data
        """
        cached = await self.get(key)
        if cached is not None:
            logger.debug(f"Cache hit: {key}")
            return cached

        logger.debug(f"Cache miss: {key}")
        data = await fetch_func()
        if data is not None:
            await self.set(key, data, ttl_seconds)
        return data

    # Market data caching methods
    async def get_market_internals(self, symbols: list) -> dict | None:
        """Get cached market internals"""
        key = f"market:internals:{':'.join(sorted(symbols))}"
        return await self.get(key)

    async def set_market_internals(self, symbols: list, data: dict) -> bool:
        """Cache market internals"""
        key = f"market:internals:{':'.join(sorted(symbols))}"
        return await self.set(key, data, self.ttl_market_internals)

    async def get_ohlc(self, symbol: str, timeframe: str) -> list | None:
        """Get cached OHLC data"""
        key = f"ohlc:{symbol}:{timeframe}"
        return await self.get(key)

    async def set_ohlc(self, symbol: str, timeframe: str, data: list) -> bool:
        """Cache OHLC data"""
        key = f"ohlc:{symbol}:{timeframe}"
        return await self.set(key, data, self.ttl_ohlc)

    async def get_market_breadth(self) -> dict | None:
        """Get cached market breadth"""
        return await self.get("market:breadth")

    async def set_market_breadth(self, data: dict) -> bool:
        """Cache market breadth"""
        return await self.set("market:breadth", data, self.ttl_breadth)

    async def get_llm_response(self, cache_key: str) -> str | None:
        """Get cached LLM response"""
        return await self.get(f"llm:{cache_key}")

    async def set_llm_response(self, cache_key: str, response: str) -> bool:
        """Cache LLM response"""
        return await self.set(f"llm:{cache_key}", response, self.ttl_llm_response)

    async def invalidate_symbol(self, symbol: str):
        """Invalidate all cache entries for a symbol"""
        if not self.is_connected:
            return
        try:
            pattern = f"*:{symbol}:*"
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)
            if keys:
                await self._client.delete(*keys)
                logger.debug(f"Invalidated {len(keys)} cache entries for {symbol}")
        except Exception as e:
            logger.debug(f"Cache invalidation error: {e}")

    async def clear_all(self):
        """Clear all cache entries"""
        if not self.is_connected:
            return
        try:
            await self._client.flushdb()
            logger.info("Cache cleared")
        except Exception as e:
            logger.error(f"Cache clear error: {e}")


# Global cache instance
_cache_instance: CacheService | None = None


async def get_cache() -> CacheService:
    """Get or create cache service instance"""
    global _cache_instance
    if _cache_instance is None:
        _cache_instance = CacheService()
        await _cache_instance.connect()
    return _cache_instance


async def close_cache():
    """Close cache connection"""
    global _cache_instance
    if _cache_instance:
        await _cache_instance.disconnect()
        _cache_instance = None
