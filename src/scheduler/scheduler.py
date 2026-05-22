"""Background scheduler for market data collection"""

import asyncio
from datetime import datetime, date, time as dtime, timedelta
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

    def _get_db_session(self):
        try:
            from src.core.database import DatabaseManager
            from src.core.config import get_settings
            settings = get_settings()
            db = DatabaseManager(settings.database_url)
            return db.get_session()
        except Exception as e:
            logger.warning(f"Database not available: {e}")
            return None

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

        from src.core.database import ScreenerSnapshot

        session = self._get_db_session()

        for screener_type in ['gainers', 'losers', 'most_active']:
            try:
                data = self._yahoo_client.get_screener_data(screener_type)
                if data and self._cache:
                    await self._cache.set(f'screener:{screener_type}', data, 1800)
                    logger.debug(f"Cached {screener_type}: {len(data)} results")

                if session and data:
                    today = date.today()
                    for item in data:
                        snapshot = ScreenerSnapshot(
                            snapshot_date=today,
                            screener_type=screener_type,
                            symbol=item.get('symbol', ''),
                            rank=item.get('rank', 0),
                            price=item.get('price'),
                            change_pct=item.get('change_pct'),
                            volume=item.get('volume'),
                            market_cap=item.get('market_cap'),
                            extra_data=item,
                        )
                        session.merge(snapshot)
                    session.commit()
                    logger.debug(f"Wrote {len(data)} {screener_type} records to DB")
            except Exception as e:
                logger.error(f"Error fetching {screener_type} screener: {e}")
                if session:
                    session.rollback()

        if session:
            session.close()

    async def _fetch_breadth_data(self):
        """Fetch market breadth data"""
        if not self._is_market_hours():
            return

        from src.core.database import BreadthSnapshot

        try:
            from src.data.market_breadth import MarketBreadthCollector
            collector = MarketBreadthCollector()
            data = collector.get_market_internals()
            if data and self._cache:
                await self._cache.set('market:breadth', data, 60)
                logger.debug("Cached breadth data")

            session = self._get_db_session()
            if session and data:
                today = date.today()
                snapshot = BreadthSnapshot(
                    date=today,
                    nyse_advancing=data.get('nyse_advancing'),
                    nyse_declining=data.get('nyse_declining'),
                    nyse_unchanged=data.get('nyse_unchanged'),
                    nyse_ad_ratio=data.get('nyse_ad_ratio'),
                    nasdaq_advancing=data.get('nasdaq_advancing'),
                    nasdaq_declining=data.get('nasdaq_declining'),
                    nasdaq_unchanged=data.get('nasdaq_unchanged'),
                    nasdaq_ad_ratio=data.get('nasdaq_ad_ratio'),
                    new_highs_52w=data.get('new_highs'),
                    new_lows_52w=data.get('new_lows'),
                    tick_avg_30m=data.get('tick_30min_avg'),
                    vold_nyse=data.get('nyse_vold'),
                    mcclellan_osc=data.get('mcclellan_oscillator'),
                    mcclellan_sum=data.get('mcclellan_summation'),
                )
                session.merge(snapshot)
                session.commit()
                logger.debug(f"Wrote breadth snapshot for {today} to DB")
                session.close()
        except Exception as e:
            logger.error(f"Error fetching breadth data: {e}")

    async def _compute_symbol_stats(self):
        """Compute and store daily symbol statistics (52W levels, SMAs, etc.)"""
        from src.core.database import SymbolStats, PriceData
        import numpy as np

        session = self._get_db_session()
        if not session:
            return

        try:
            symbols = ['SPY', 'QQQ', 'IWM', 'DIA', 'AAPL', 'TSLA', 'NVDA', 'BTC-USD', 'ETH-USD']
            today = date.today()

            for symbol in symbols:
                try:
                    rows = session.query(PriceData).filter(
                        PriceData.symbol == symbol,
                        PriceData.timeframe == '1d',
                        PriceData.timestamp >= today - timedelta(days=365),
                    ).order_by(PriceData.timestamp.desc()).limit(252).all()

                    if len(rows) < 20:
                        continue

                    closes = [r.close_price for r in reversed(rows)]
                    highs = [r.high_price for r in reversed(rows)]
                    lows = [r.low_price for r in reversed(rows)]
                    volumes = [r.volume for r in reversed(rows)]

                    current_price = closes[-1]

                    high_52w = max(highs)
                    low_52w = min(lows)
                    pct_from_52w_high = ((current_price - high_52w) / high_52w * 100) if high_52w else None
                    pct_from_52w_low = ((current_price - low_52w) / low_52w * 100) if low_52w else None

                    sma_20 = float(np.mean(closes[-20:])) if len(closes) >= 20 else None
                    sma_50 = float(np.mean(closes[-50:])) if len(closes) >= 50 else None
                    sma_200 = float(np.mean(closes[-200:])) if len(closes) >= 200 else None

                    avg_volume_20d = int(np.mean(volumes[-20:])) if len(volumes) >= 20 else None
                    avg_volume_50d = int(np.mean(volumes[-50:])) if len(volumes) >= 50 else None

                    if len(closes) >= 15:
                        tr_list = []
                        for i in range(1, min(15, len(closes))):
                            tr = max(highs[i] - lows[i], abs(highs[i] - closes[i-1]), abs(lows[i] - closes[i-1]))
                            tr_list.append(tr)
                        atr_14 = float(np.mean(tr_list)) if tr_list else None
                    else:
                        atr_14 = None

                    stats = SymbolStats(
                        symbol=symbol,
                        date=today,
                        high_52w=high_52w,
                        low_52w=low_52w,
                        pct_from_52w_high=pct_from_52w_high,
                        pct_from_52w_low=pct_from_52w_low,
                        sma_20=sma_20,
                        sma_50=sma_50,
                        sma_200=sma_200,
                        atr_14=atr_14,
                        avg_volume_20d=avg_volume_20d,
                        avg_volume_50d=avg_volume_50d,
                        prev_close=closes[-2] if len(closes) >= 2 else None,
                    )
                    session.merge(stats)
                except Exception as e:
                    logger.warning(f"Error computing stats for {symbol}: {e}")
                    continue

            session.commit()
            logger.info(f"Computed symbol stats for {len(symbols)} symbols")
        except Exception as e:
            logger.error(f"Error computing symbol stats: {e}")
            session.rollback()
        finally:
            session.close()
