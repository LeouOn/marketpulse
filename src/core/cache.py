"""
Redis cache manager for MarketPulse
Provides caching capabilities for market data and API responses
"""

import json
import os
from typing import Optional, Any, Dict
from datetime import timedelta
import redis.asyncio as redis
from loguru import logger


class CacheManager:
    """Manages Redis caching for market data and API responses"""

    def __init__(self, redis_url: Optional[str] = None):
        """
        Initialize cache manager

        Args:
            redis_url: Redis connection URL (defaults to environment variable)
        """
        self.redis_url = redis_url or os.getenv(
            "REDIS_URL", "redis://localhost:6379/0"
        )
        self._client: Optional[redis.Redis] = None
        self._connected = False

    async def connect(self) -> bool:
        """
        Establish connection to Redis

        Returns:
            True if connection successful, False otherwise
        """
        try:
            self._client = redis.from_url(
                self.redis_url,
                encoding="utf-8",
                decode_responses=True,
                socket_connect_timeout=5,
            )
            # Test connection
            await self._client.ping()
            self._connected = True
            logger.info(f"Connected to Redis at {self.redis_url}")
            return True
        except Exception as e:
            logger.error(f"Failed to connect to Redis: {e}")
            self._connected = False
            return False

    async def disconnect(self):
        """Close Redis connection"""
        if self._client:
            await self._client.close()
            self._connected = False
            logger.info("Disconnected from Redis")

    @property
    def is_connected(self) -> bool:
        """Check if Redis is connected"""
        return self._connected

    async def get(self, key: str) -> Optional[Any]:
        """
        Get value from cache

        Args:
            key: Cache key

        Returns:
            Cached value or None if not found/error
        """
        if not self._connected or not self._client:
            return None

        try:
            value = await self._client.get(key)
            if value:
                return json.loads(value)
            return None
        except Exception as e:
            logger.warning(f"Cache get error for key '{key}': {e}")
            return None

    async def set(
        self,
        key: str,
        value: Any,
        ttl: Optional[int] = None,
    ) -> bool:
        """
        Set value in cache

        Args:
            key: Cache key
            value: Value to cache (must be JSON serializable)
            ttl: Time to live in seconds (None for no expiration)

        Returns:
            True if successful, False otherwise
        """
        if not self._connected or not self._client:
            return False

        try:
            serialized = json.dumps(value)
            if ttl:
                await self._client.setex(key, ttl, serialized)
            else:
                await self._client.set(key, serialized)
            return True
        except Exception as e:
            logger.warning(f"Cache set error for key '{key}': {e}")
            return False

    async def delete(self, key: str) -> bool:
        """
        Delete key from cache

        Args:
            key: Cache key

        Returns:
            True if deleted, False otherwise
        """
        if not self._connected or not self._client:
            return False

        try:
            await self._client.delete(key)
            return True
        except Exception as e:
            logger.warning(f"Cache delete error for key '{key}': {e}")
            return False

    async def exists(self, key: str) -> bool:
        """
        Check if key exists in cache

        Args:
            key: Cache key

        Returns:
            True if exists, False otherwise
        """
        if not self._connected or not self._client:
            return False

        try:
            return await self._client.exists(key) > 0
        except Exception as e:
            logger.warning(f"Cache exists error for key '{key}': {e}")
            return False

    async def clear_pattern(self, pattern: str) -> int:
        """
        Clear all keys matching pattern

        Args:
            pattern: Key pattern (e.g., "market:*")

        Returns:
            Number of keys deleted
        """
        if not self._connected or not self._client:
            return 0

        try:
            keys = []
            async for key in self._client.scan_iter(match=pattern):
                keys.append(key)

            if keys:
                return await self._client.delete(*keys)
            return 0
        except Exception as e:
            logger.warning(f"Cache clear pattern error for '{pattern}': {e}")
            return 0

    # Convenience methods for market data

    async def get_market_data(self, symbol: str) -> Optional[Dict]:
        """Get cached market data for symbol"""
        return await self.get(f"market:data:{symbol}")

    async def set_market_data(self, symbol: str, data: Dict, ttl: int = 60) -> bool:
        """Cache market data for symbol (default 60s TTL)"""
        return await self.set(f"market:data:{symbol}", data, ttl)

    async def get_dashboard_data(self) -> Optional[Dict]:
        """Get cached dashboard data"""
        return await self.get("dashboard:data")

    async def set_dashboard_data(self, data: Dict, ttl: int = 30) -> bool:
        """Cache dashboard data (default 30s TTL)"""
        return await self.set("dashboard:data", data, ttl)

    async def get_historical_data(
        self, symbol: str, timeframe: str, limit: int
    ) -> Optional[list]:
        """Get cached historical data"""
        key = f"historical:{symbol}:{timeframe}:{limit}"
        return await self.get(key)

    async def set_historical_data(
        self, symbol: str, timeframe: str, limit: int, data: list, ttl: int = 300
    ) -> bool:
        """Cache historical data (default 5min TTL)"""
        key = f"historical:{symbol}:{timeframe}:{limit}"
        return await self.set(key, data, ttl)

    async def get_llm_analysis(self, cache_key: str) -> Optional[Dict]:
        """Get cached LLM analysis"""
        return await self.get(f"llm:analysis:{cache_key}")

    async def set_llm_analysis(
        self, cache_key: str, analysis: Dict, ttl: int = 300
    ) -> bool:
        """Cache LLM analysis (default 5min TTL)"""
        return await self.set(f"llm:analysis:{cache_key}", analysis, ttl)

    async def invalidate_market_cache(self, symbol: Optional[str] = None):
        """
        Invalidate market data cache

        Args:
            symbol: Specific symbol to invalidate, or None for all
        """
        if symbol:
            await self.delete(f"market:data:{symbol}")
        else:
            await self.clear_pattern("market:data:*")

        # Always invalidate dashboard when market data changes
        await self.delete("dashboard:data")


# Global cache instance
cache_manager = CacheManager()
