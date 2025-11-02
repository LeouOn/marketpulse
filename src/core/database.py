"""MarketPulse Database Models
SQLAlchemy models for market data storage
"""

from sqlalchemy import Column, Integer, String, Float, DateTime, Boolean, Text, UniqueConstraint
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from datetime import datetime

Base = declarative_base()


class PriceData(Base):
    """OHLCV price data model"""
    __tablename__ = 'prices'
    __table_args__ = (UniqueConstraint('symbol', 'timeframe', 'timestamp', name='_symbol_timeframe_timestamp_uc'),)
    
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
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<PriceData(symbol='{self.symbol}', timestamp='{self.timestamp}', close={self.close_price})>"


class MarketInternals(Base):
    """Market internals analysis model"""
    __tablename__ = 'market_internals'
    __table_args__ = (UniqueConstraint('symbol', 'timestamp', name='_symbol_timestamp_uc'),)
    
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
    __tablename__ = 'llm_insights'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    analysis_type = Column(String(50), nullable=False, index=True)
    model_used = Column(String(50), nullable=False)
    input_data = Column(JSONB)
    analysis_result = Column(Text)
    confidence_score = Column(Float)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<LLMInsight(symbol='{self.symbol}', analysis_type='{self.analysis_type}', model='{self.model_used}')>"


class Alert(Base):
    """Market alerts and signals model"""
    __tablename__ = 'alerts'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    alert_type = Column(String(50), nullable=False, index=True)
    timestamp = Column(DateTime(timezone=True), nullable=False, index=True)
    trigger_condition = Column(Text)
    message = Column(Text)
    severity = Column(String(20), default='INFO', index=True)
    acknowledged = Column(Boolean, default=False, index=True)
    resolved_at = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<Alert(symbol='{self.symbol}', type='{self.alert_type}', severity='{self.severity}')>"


class MarketRegime(Base):
    """Market regime classification model"""
    __tablename__ = 'market_regime'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    symbol = Column(String(20), nullable=False, index=True)
    regime_type = Column(String(50), nullable=False, index=True)
    confidence = Column(Float, nullable=False)
    start_time = Column(DateTime(timezone=True), nullable=False, index=True)
    end_time = Column(DateTime(timezone=True), index=True)
    characteristics = Column(JSONB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    
    def __repr__(self):
        return f"<MarketRegime(symbol='{self.symbol}', type='{self.regime_type}', confidence={self.confidence})>"


class DatabaseManager:
    """Database connection and operations manager"""
    
    def __init__(self, database_url: str):
        self.database_url = database_url
        self.engine = None
        
    def create_engine(self):
        """Create SQLAlchemy engine"""
        from sqlalchemy import create_engine
        self.engine = create_engine(self.database_url, pool_pre_ping=True)
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
    
    def save_price_data(self, symbol: str, timeframe: str, data_list: list):
        """Save price data to database"""
        session = self.get_session()
        try:
            for data in data_list:
                price_record = PriceData(
                    symbol=symbol,
                    timeframe=timeframe,
                    timestamp=data['timestamp'],
                    open_price=data['open'],
                    high_price=data['high'],
                    low_price=data['low'],
                    close_price=data['close'],
                    volume=data['volume'],
                    trade_count=data.get('trade_count', 0),
                    vwap=data.get('vwap')
                )
                session.merge(price_record)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def save_market_internals(self, symbol: str, internals_data: dict):
        """Save market internals to database"""
        session = self.get_session()
        try:
            internals_record = MarketInternals(
                symbol=symbol,
                timestamp=internals_data['timestamp'],
                advance_decline_ratio=internals_data.get('advance_decline_ratio'),
                volume_flow=internals_data.get('volume_flow'),
                momentum_score=internals_data.get('momentum_score'),
                volatility_regime=internals_data.get('volatility_regime'),
                correlation_strength=internals_data.get('correlation_strength'),
                support_level=internals_data.get('support_level'),
                resistance_level=internals_data.get('resistance_level')
            )
            session.merge(internals_record)
            session.commit()
        except Exception as e:
            session.rollback()
            raise e
        finally:
            session.close()
    
    def get_latest_internals(self, symbol: str, limit: int = 10):
        """Get latest market internals for a symbol"""
        session = self.get_session()
        try:
            query = session.query(MarketInternals).filter(
                MarketInternals.symbol == symbol
            ).order_by(MarketInternals.timestamp.desc()).limit(limit)
            return query.all()
        finally:
            session.close()