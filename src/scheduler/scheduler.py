"""Background scheduler for market data collection"""

import asyncio
from datetime import datetime, time as dtime
from typing import Optional

from loguru import logger
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger
from apscheduler.triggers.cron import CronTrigger


class MarketScheduler:
    def __init__(self):
        self._scheduler = AsyncIOScheduler(timezone="US/Eastern")
        self._yahoo_client = None
        self._cache = None

    async def start(self):
        """Initialize clients and register all jobs"""
        from src.api.yahoo_client import YahooFinanceClient
        from src.core.cache import get_cache

        self._yahoo_client = YahooFinanceClient()
        try:
            self._cache = await get_cache()
        except Exception:
            self._cache = None

        self._register_jobs()
        self._scheduler.start()
        logger.info("MarketScheduler started with all jobs registered")

    async def stop(self):
        if self._scheduler.running:
            self._scheduler.shutdown(wait=False)
            logger.info("MarketScheduler stopped")

    def _is_market_hours(self) -> bool:
        """Check if US equity market is open (9:30-16:00 ET, Mon-Fri)"""
        from datetime import timezone
        from zoneinfo import ZoneInfo

        now = datetime.now(ZoneInfo("US/Eastern"))
        if now.weekday() >= 5:
            return False
        market_open = dtime(9, 30)
        market_close = dtime(16, 0)
        return market_open <= now.time() <= market_close

    def _register_jobs(self):
        self._scheduler.add_job(
            self._fetch_realtime_quotes,
            IntervalTrigger(seconds=30),
            id='fetch_realtime_quotes',
            name='Fetch Real-time Quotes',
            max_instances=1,
        )

        self._scheduler.add_job(
            self._fetch_screener_data,
            IntervalTrigger(minutes=30),
            id='fetch_screener_data',
            name='Fetch Screener Data',
            max_instances=1,
        )

        self._scheduler.add_job(
            self._fetch_breadth_data,
            IntervalTrigger(minutes=5),
            id='fetch_breadth_data',
            name='Fetch Breadth Data',
            max_instances=1,
        )

    async def _fetch_realtime_quotes(self):
        """Fetch current prices for tracked symbols and cache in Redis"""
        if not self._is_market_hours():
            return
        try:
            data = self._yahoo_client.get_market_internals()
            if data and self._cache:
                await self._cache.set('market:realtime', data, 30)
                logger.debug(f"Cached realtime data for {len(data)} symbols")
        except Exception as e:
            logger.error(f"Error fetching realtime quotes: {e}")

    async def _fetch_screener_data(self):
        """Fetch screener data (gainers, losers, most_active)"""
        if not self._is_market_hours():
            return
        for screener_type in ['gainers', 'losers', 'most_active']:
            try:
                data = self._yahoo_client.get_screener_data(screener_type)
                if data and self._cache:
                    await self._cache.set(f'screener:{screener_type}', data, 1800)
                    logger.debug(f"Cached {screener_type}: {len(data)} results")
            except Exception as e:
                logger.error(f"Error fetching {screener_type} screener: {e}")

    async def _fetch_breadth_data(self):
        """Fetch market breadth data"""
        if not self._is_market_hours():
            return
        try:
            from src.data.market_breadth import MarketBreadthCollector

            collector = MarketBreadthCollector()
            data = collector.get_market_internals()
            if data and self._cache:
                await self._cache.set('market:breadth', data, 60)
                logger.debug("Cached breadth data")
        except Exception as e:
            logger.error(f"Error fetching breadth data: {e}")
