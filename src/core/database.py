from datetime import datetime

from loguru import logger
from sqlalchemy import JSON, BigInteger, Boolean, Column, Date, DateTime, Float, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.pool import AsyncAdaptedQueuePool, NullPool
from sqlalchemy.sql import func


class Base(DeclarativeBase):
    pass


class PriceData(Base):
    """OHLCV price data model"""

    __tablename__ = "prices"
    __table_args__ = (UniqueConstraint("symbol", "timeframe", "timestamp", name="_symbol_timeframe_timestamp_uc"), {"schema": "market_data"})

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    open_price = Column(Float, nullable=False)
    high_price = Column(Float, nullable=False)
    low_price = Column(Float, nullable=False)
    close_price = Column(Float, nullable=False)
    volume = Column(Integer, default=0)
    trade_count = Column(Integer, default=0)
    vwap = Column(Float)
    adjusted_close = Column(Float)
    split_factor = Column(Float, default=1.0)
    dividend_amount = Column(Float, default=0.0)
    source = Column(String(20), default='yahoo')
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<PriceData(symbol='{self.symbol}', timestamp='{self.timestamp}', close={self.close_price})>"


class MarketInternals(Base):
    """Market internals analysis model"""

    __tablename__ = "internals"
    __table_args__ = (UniqueConstraint("symbol", "timestamp", name="_symbol_timestamp_uc"), {"schema": "market_data"})

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    advance_decline_ratio = Column(Float)
    volume_flow = Column(Float)
    momentum_score = Column(Float)
    volatility_regime = Column(String(20))
    correlation_strength = Column(Float)
    support_level = Column(Float)
    resistance_level = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<MarketInternals(symbol='{self.symbol}', timestamp='{self.timestamp}', regime='{self.volatility_regime}')>"


class LLMInsight(Base):
    """LLM analysis results model"""

    __tablename__ = "llm_insights"
    __table_args__ = ({"schema": "analysis"},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    analysis_type = Column(String(50), nullable=False, index=True)
    model_used = Column(String(50), nullable=False)
    input_data = Column(JSON)
    analysis_result = Column(Text)
    confidence_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<LLMInsight(symbol='{self.symbol}', analysis_type='{self.analysis_type}', model='{self.model_used}')>"


class Alert(Base):
    """Market alerts and signals model"""

    __tablename__ = "alerts"
    __table_args__ = ({"schema": "analysis"},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    trigger_condition = Column(Text)
    message = Column(Text)
    severity = Column(String(20), default="INFO", index=True)
    acknowledged = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Alert(symbol='{self.symbol}', type='{self.alert_type}', severity='{self.severity}')>"


class MarketRegime(Base):
    """Market regime classification model"""

    __tablename__ = "market_regime"
    __table_args__ = ({"schema": "analysis"},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    regime_type = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), index=True)
    characteristics = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<MarketRegime(symbol='{self.symbol}', type='{self.regime_type}', confidence={self.confidence})>"


class Symbol(Base):
    __tablename__ = "symbols"
    __table_args__ = (UniqueConstraint("symbol", name="_symbol_uc"), {"schema": "market_data"})

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), unique=True, nullable=False, index=True)
    name = Column(String(200))
    asset_type = Column(String(20), nullable=False)
    exchange = Column(String(20))
    sector = Column(String(50), index=True)
    industry = Column(String(100))
    currency = Column(String(3), default='USD')
    lot_size = Column(Float, default=1.0)
    tick_size = Column(Float, default=0.01)
    is_active = Column(Boolean, default=True, index=True)
    yahoo_symbol = Column(String(20))
    alpaca_symbol = Column(String(20))
    data_source = Column(String(20), default='yahoo')
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    def __repr__(self):
        return f"<Symbol(symbol='{self.symbol}', name='{self.name}', asset_type='{self.asset_type}')>"


class SymbolStats(Base):
    __tablename__ = "symbol_stats"
    __table_args__ = (UniqueConstraint("symbol", "date", name="_symbol_date_uc"), {"schema": "market_data"})

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    date = Column(Date, nullable=False)
    high_52w = Column(Float)
    low_52w = Column(Float)
    pct_from_52w_high = Column(Float)
    pct_from_52w_low = Column(Float)
    avg_volume_20d = Column(Integer)
    avg_volume_50d = Column(Integer)
    sma_20 = Column(Float)
    sma_50 = Column(Float)
    sma_200 = Column(Float)
    atr_14 = Column(Float)
    beta = Column(Float)
    market_cap = Column(BigInteger)
    pe_ratio = Column(Float)
    prev_close = Column(Float)
    day_range_pct = Column(Float)
    year_high_date = Column(Date)
    year_low_date = Column(Date)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<SymbolStats(symbol='{self.symbol}', date='{self.date}', market_cap={self.market_cap})>"


class ScreenerSnapshot(Base):
    __tablename__ = "screener_snapshots"
    __table_args__ = (
        UniqueConstraint("snapshot_date", "screener_type", "symbol", name="_snapshot_screener_symbol_uc"),
        {"schema": "market_data"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    snapshot_date = Column(Date, nullable=False)
    screener_type = Column(String(20), nullable=False)
    symbol = Column(String(20), nullable=False, index=True)
    rank = Column(Integer, nullable=False)
    price = Column(Float)
    change_pct = Column(Float)
    volume = Column(BigInteger)
    market_cap = Column(BigInteger)
    avg_volume_3m = Column(BigInteger)
    relative_volume = Column(Float)
    extra_data = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<ScreenerSnapshot(date='{self.snapshot_date}', type='{self.screener_type}', symbol='{self.symbol}', rank={self.rank})>"


class BreadthSnapshot(Base):
    __tablename__ = "breadth_snapshots"
    __table_args__ = (UniqueConstraint("date", name="_breadth_date_uc"), {"schema": "market_data"})

    id = Column(Integer, primary_key=True, autoincrement=True)
    date = Column(Date, nullable=False)
    nyse_advancing = Column(Integer)
    nyse_declining = Column(Integer)
    nyse_unchanged = Column(Integer)
    nyse_ad_ratio = Column(Float)
    nasdaq_advancing = Column(Integer)
    nasdaq_declining = Column(Integer)
    nasdaq_unchanged = Column(Integer)
    nasdaq_ad_ratio = Column(Float)
    new_highs_52w = Column(Integer)
    new_lows_52w = Column(Integer)
    tick_avg_30m = Column(Float)
    vold_nyse = Column(BigInteger)
    mcclellan_osc = Column(Float)
    mcclellan_sum = Column(Float)
    trin = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<BreadthSnapshot(date='{self.date}', nyse_ad_ratio={self.nyse_ad_ratio})>"


class DataFetchLog(Base):
    __tablename__ = "data_fetch_log"
    __table_args__ = ({"schema": "market_data"},)

    id = Column(Integer, primary_key=True, autoincrement=True)
    source = Column(String(20), nullable=False)
    endpoint = Column(String(200), nullable=False)
    symbols = Column(Text)
    status = Column(String(10), nullable=False)
    response_ms = Column(Integer)
    bars_fetched = Column(Integer, default=0)
    error_message = Column(Text)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<DataFetchLog(source='{self.source}', endpoint='{self.endpoint}', status='{self.status}')>"


class Indicator(Base):
    __tablename__ = "indicators"
    __table_args__ = (
        UniqueConstraint("symbol", "timeframe", "timestamp", "indicator_type", "params", name="_indicator_uc"),
        {"schema": "analysis"},
    )

    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timeframe = Column(String(10), nullable=False)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    indicator_type = Column(String(30), nullable=False)
    params = Column(JSON, nullable=False)
    value = Column(Float)
    values = Column(JSON)
    created_at = Column(DateTime(timezone=True), server_default=func.now())

    def __repr__(self):
        return f"<Indicator(symbol='{self.symbol}', type='{self.indicator_type}', timeframe='{self.timeframe}')>"


class DatabaseManager:
    """Database connection and operations manager with connection pooling"""

    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        self._pool_size = 5
        self._max_overflow = 10
        self._pool_timeout = 30
        self._pool_recycle = 3600

    def create_engine(self):
        """Create SQLAlchemy engine with connection pooling"""
        from sqlalchemy import create_engine

        is_sqlite = "sqlite" in self.database_url.lower()
        is_postgres = "postgresql" in self.database_url.lower()

        if is_sqlite:
            self.engine = create_engine(
                self.database_url, poolclass=NullPool, connect_args={"check_same_thread": False}
            )
        elif is_postgres:
            # Try to use asyncpg, fall back to sync if not available
            try:
                self.engine = create_engine(
                    self.database_url,
                    poolclass=AsyncAdaptedQueuePool,
                    pool_size=self._pool_size,
                    max_overflow=self._max_overflow,
                    pool_timeout=self._pool_timeout,
                    pool_recycle=self._pool_recycle,
                    pool_pre_ping=True,
                )
                logger.info(f"Database pool configured: size={self._pool_size}, max_overflow={self._max_overflow}")
            except Exception as e:
                logger.warning(f"Failed to create async pool, trying sync: {e}")
                # Fall back to regular sync engine
                self.engine = create_engine(
                    self.database_url, pool_pre_ping=True, pool_size=self._pool_size, max_overflow=self._max_overflow
                )
        else:
            self.engine = create_engine(self.database_url)

        return self.engine

    def create_tables(self):
        """Create all database tables"""
        if not self.engine:
            self.create_engine()
        Base.metadata.create_all(bind=self.engine)

    def get_session(self):
        """Get database session"""
        from sqlalchemy.orm import sessionmaker

        if not self.engine:
            self.create_engine()
        Session = sessionmaker(bind=self.engine)
        return Session()

    async def get_async_session(self):
        """Get async database session for use with async code"""
        from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine

        is_sqlite = "sqlite" in self.database_url.lower()

        if is_sqlite:
            async_engine = create_async_engine(
                self.database_url.replace("sqlite://", "sqlite+aiosqlite://"), poolclass=NullPool
            )
        else:
            async_url = self.database_url.replace("postgresql://", "postgresql+asyncpg://")
            async_engine = create_async_engine(
                async_url,
                pool_size=self._pool_size,
                max_overflow=self._max_overflow,
                pool_timeout=self._pool_timeout,
                pool_recycle=self._pool_recycle,
                pool_pre_ping=True,
            )

        async_session = AsyncSession(async_engine, expire_on_commit=False)
        return async_session

    def save_price_data(self, symbol: str, timeframe: str, data_list: list):
        """Save price data to database with OHLC validation"""
        session = self.get_session()
        try:
            for data in data_list:
                # Validate OHLC consistency before saving
                ohlc_valid, ohlc_issues = self._validate_ohlc(
                    data.get("open"), data.get("high"), data.get("low"), data.get("close")
                )
                if not ohlc_valid:
                    logger.warning(f"Skipping invalid OHLC for {symbol}: {ohlc_issues}")
                    continue

                price_record = PriceData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=data["timestamp"],
                    open_price=data["open"],
                    high_price=data["high"],
                    low_price=data["low"],
                    close_price=data["close"],
                    volume=data["volume"],
                    trade_count=data.get("trade_count", 0),
                    vwap=data.get("vwap"),
                )
                session.merge(price_record)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def _validate_ohlc(self, open_price, high_price, low_price, close_price) -> tuple:
        """Validate OHLC data consistency. Returns (is_valid, issues)"""
        issues = []

        if None in (open_price, high_price, low_price, close_price):
            return False, ["One or more OHLC values are None"]

        if any(p <= 0 for p in [open_price, high_price, low_price, close_price]):
            issues.append(f"Non-positive price: O={open_price}, H={high_price}, L={low_price}, C={close_price}")

        if high_price < max(open_price, close_price):
            issues.append(f"High {high_price} < max(O={open_price}, C={close_price})")

        if low_price > min(open_price, close_price):
            issues.append(f"Low {low_price} > min(O={open_price}, C={close_price})")

        return len(issues) == 0, issues

    def save_market_internals(self, symbol: str, internals_data: dict):
        """Save market internals to database with validation"""
        # Validate price ranges for critical symbols
        if symbol.upper() in ["SPY", "QQQ", "VIX"]:
            price = internals_data.get("price")
            if price is not None:
                valid, issues = self._validate_symbol_price(symbol.upper(), price)
                if not valid:
                    logger.warning(f"Skipping invalid {symbol} internals: {issues}")
                    return  # Skip saving invalid data

        session = self.get_session()
        try:
            internals_record = MarketInternals(
                symbol=symbol,
                timestamp=internals_data["timestamp"],
                advance_decline_ratio=internals_data.get("advance_decline_ratio"),
                volume_flow=internals_data.get("volume_flow"),
                momentum_score=internals_data.get("momentum_score"),
                volatility_regime=internals_data.get("volatility_regime"),
                correlation_strength=internals_data.get("correlation_strength"),
                support_level=internals_data.get("support_level"),
                resistance_level=internals_data.get("resistance_level"),
            )
            session.merge(internals_record)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()

    def _validate_symbol_price(self, symbol: str, price: float) -> tuple:
        """Validate symbol price is within reasonable bounds. Returns (is_valid, issues)"""
        from ..core.validators import REASONABLE_RANGES

        issues = []
        if price is None or price <= 0:
            return False, ["price is None or <= 0"]

        if symbol in REASONABLE_RANGES:
            min_p, max_p = REASONABLE_RANGES[symbol]
            if price < min_p:
                issues.append(f"{symbol} price ${price:.2f} below minimum ${min_p}")
            if price > max_p:
                issues.append(f"{symbol} price ${price:.2f} above maximum ${max_p}")

        return len(issues) == 0, issues

    def save_llm_insight(
        self,
        symbol: str,
        analysis_type: str,
        input_data: dict,
        analysis_result: str,
        model_used: str = "lm_studio_fast",
        confidence_score: float = 0.8,
    ):
        """Save LLM insight to database"""
        session = self.get_session()
        try:
            insight_record = LLMInsight(
                symbol=symbol,
                timestamp=datetime.now(),
                analysis_type=analysis_type,
                model_used=model_used,
                input_data=input_data,
                analysis_result=analysis_result,
                confidence_score=confidence_score,
            )
            session.merge(insight_record)
            session.commit()
            logger.info(f"💾 LLM insight saved for {symbol}")
        except Exception as e:
            session.rollback()
            logger.error(f"❌ Error saving LLM insight: {e}")
            raise e
        finally:
            session.close()

    def get_latest_internals(self, symbol: str, limit: int = 10):
        """Get latest market internals for a symbol"""
        session = self.get_session()
        try:
            query = (
                session.query(MarketInternals)
                .filter(MarketInternals.symbol == symbol)
                .order_by(MarketInternals.timestamp.desc())
                .limit(limit)
            )
            return query.all()
        finally:
            session.close()

    def save_user_comment(self, comment_data: dict):
        """Save user comment on an LLM analysis"""
        session = self.get_session()
        try:
            from sqlalchemy import text

            session.execute(
                text(
                    "CREATE TABLE IF NOT EXISTS user_comments ("
                    "id SERIAL PRIMARY KEY, "
                    "analysis_id VARCHAR(100), "
                    "user_id VARCHAR(100), "
                    "comment TEXT, "
                    "timestamp VARCHAR(100), "
                    "created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP)"
                )
            )
            session.execute(
                text(
                    "INSERT INTO user_comments (analysis_id, user_id, comment, timestamp) "
                    "VALUES (:analysis_id, :user_id, :comment, :timestamp)"
                ),
                {
                    "analysis_id": comment_data.get("analysis_id", ""),
                    "user_id": comment_data.get("user_id", "anonymous"),
                    "comment": comment_data.get("comment", ""),
                    "timestamp": comment_data.get("timestamp", datetime.now().isoformat()),
                },
            )
            session.commit()
            logger.info(f"User comment saved for analysis {comment_data.get('analysis_id')}")
        except Exception as e:
            session.rollback()
            logger.error(f"Error saving user comment: {e}")
            raise e
        finally:
            session.close()

    def get_analysis_conversation(self, analysis_id: str):
        """Get conversation history for an analysis"""
        session = self.get_session()
        try:
            from sqlalchemy import text

            result = session.execute(
                text("SELECT * FROM user_comments WHERE analysis_id = :analysis_id ORDER BY created_at ASC"),
                {"analysis_id": analysis_id},
            )
            rows = result.fetchall()
            return [
                {
                    "id": row[0],
                    "analysis_id": row[1],
                    "user_id": row[2],
                    "comment": row[3],
                    "timestamp": row[4],
                    "created_at": str(row[5]) if len(row) > 5 else None,
                }
                for row in rows
            ]
        except Exception as e:
            logger.error(f"Error retrieving conversation history: {e}")
            return []
        finally:
            session.close()

    def configure_pool(
        self, pool_size: int = 5, max_overflow: int = 10, pool_timeout: int = 30, pool_recycle: int = 3600
    ):
        """Configure connection pool settings"""
        self._pool_size = pool_size
        self._max_overflow = max_overflow
        self._pool_timeout = pool_timeout
        self._pool_recycle = pool_recycle
        if self.engine:
            logger.warning("Pool settings will take effect on next engine creation")

    def close(self):
        """Close database engine and all connections"""
        if self.engine:
            self.engine.dispose()
            logger.info("Database engine closed")
